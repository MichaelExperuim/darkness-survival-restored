#!/usr/bin/env python3
"""Raw TCP capture listener for darkness.apk's dead backend.

The game does NOT speak HTTP -- confirmed via disassembly of
libcocos2dcpp.so, GameNet::connectLoginServer()/connectGameServer() call
ZPPTCPNetwork::connectServer(host, port) with a custom binary protocol on:
  - rpg1.dungeonheroine.cafe24.com:4776  (login server)
  - rpg1.dungeonheroine.cafe24.com:4778  (game server)

This listens on both ports, accepts connections, and logs every byte the
client sends (hex + ascii to stdout, raw bytes to a .bin file per
connection).

Every complete [2-byte length][ZPPCoder-encoded blob] packet is also
decoded on the fly via zppcoder.py (reverse-engineered from the binary's
ZPPCoder::encode/decode) and printed as plaintext -- see zppcoder.py for
how the key/table were recovered.

IMPORTANT: a single reply is not enough to keep the client alive. Traced the
real branch logic in UILayer::networking() directly (raw disassembly, not
just the decompiler): every frame it calls GameNet::getNetworkStatus(), and
unless that returns exactly -5 ("packet ready"), it shows a "connection
lost" popup AND unconditionally calls GameNet::disconnect() -- which hits a
real use-after-free bug in the original binary (ZPPTCPNetwork::disconnectServer
calls pthread_mutex_lock on an already-destroyed mutex) and crashes with
SIGABRT. Confirmed via live crash + tombstone backtraces on 2026-07-10.

The catch: GameNet::getNetworkStatus() resets its cached status to -2
("connected, nothing new") at the top of EVERY poll, and only bumps it back
to -5 if fresh bytes arrived that exact frame. So a single one-shot reply
satisfies -5 for exactly one frame, then reverts to -2 on the next poll (no
new data) -- which is "not -5" -- triggering disconnect() immediately after.
Fix: keep a steady stream of placeholder packets flowing for as long as the
connection is open, faster than the client's poll rate, so there's always
"fresh" data waiting. Tune RESPONSE_PAYLOAD/KEEPALIVE_INTERVAL below as we
learn more about what the client expects.

Point the game at this host by redirecting DNS for
rpg1.dungeonheroine.cafe24.com to this machine's LAN IP (dnsmasq, or a
rooted device's /system/etc/hosts) -- or, if the APK's hostname string has
been patched to 127.0.0.1, just use `adb reverse tcp:4776 tcp:4776` and
`adb reverse tcp:4778 tcp:4778` over USB instead, no DNS/root needed.

Usage: sudo python3 tcp_probe.py         # binds 4776 and 4778
"""
import datetime
import os
import socket
import sys
import threading

import zppcoder

PORTS = (4776, 4778)
CAPTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")

# Response payload sent once per connection (see SEND_MODE below).
#
# Byte 0 = packet type, read directly by GameNet::getPacketType() (offset
# 0x200c into the GameNet object = 0xc + 0x2000, i.e. byte 0 of the decoded
# incoming buffer). Valid range 1-42.
#
# Byte 1 = "result" code, read by GameNet::getResult() (offset 0x200d, byte
# 1 of the decoded buffer). Traced the actual type=1 handler in
# UILayer::networking() directly: result==1 branches away entirely;
# result==0 or result==2 both take the "success" path (syncServerTime,
# closeConnectingServer, dispatch a success event) but result==2
# additionally triggers extra processing afterward that result==0 skips.
# Using type=1/result=2 to exercise the fuller success path.
#
# Almost every packet-type handler in UILayer::networking() calls
# GameNet::disconnect() right after processing -- confirmed by reading
# every case block, not just this one. That's NORMAL protocol behavior
# (single request -> single response -> disconnect), not an error path.
# The crash we hit earlier was disconnect()'s own pre-existing
# use-after-free bug (ZPPTCPNetwork::disconnectServer locks an
# already-destroyed mutex), which fires on some connect/disconnect timings
# regardless of whether the response was "successful."
RESPONSE_PAYLOAD = bytes([1, 2])

# "single": send RESPONSE_PAYLOAD once per connection, matching the game's
# real request-response-disconnect design -- then just keep the socket open
# (no more sends) so the client can still recv() again if it sends another
# request before disconnecting on its own.
# "stream": keep resending every KEEPALIVE_INTERVAL seconds (old approach,
# useful for avoiding the idle-disconnect crash path but doesn't match the
# protocol's real design and can cause the client to receive overlapping
# packets it doesn't expect).
SEND_MODE = "single"
KEEPALIVE_INTERVAL = 0.05


def hexdump(data: bytes) -> str:
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"  {i:08x}  {hex_part:<47}  {ascii_part}")
    return "\n".join(lines)


def keepalive_sender(conn: socket.socket, stop: threading.Event, tag: str):
    sent = 0
    try:
        while not stop.is_set():
            wire = zppcoder.wrap_wire_packet(RESPONSE_PAYLOAD)
            conn.sendall(wire)
            sent += 1
            stop.wait(KEEPALIVE_INTERVAL)
    except OSError:
        pass  # socket closed out from under us, handle_client is winding down
    finally:
        print(f"[{tag}] keepalive sender stopped after {sent} packets", flush=True)


def handle_client(conn: socket.socket, addr, port: int):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    tag = f"{ts}_{addr[0]}_{addr[1]}_port{port}"
    binpath = os.path.join(CAPTURE_DIR, f"{tag}.bin")
    print(f"\n=== [{ts}] connection from {addr[0]}:{addr[1]} on port {port} ===", flush=True)

    all_bytes = bytearray()
    pending = bytearray()  # unconsumed bytes awaiting a complete packet
    conn.settimeout(0.5)
    stop_keepalive = threading.Event()
    sender = None
    if SEND_MODE == "stream":
        sender = threading.Thread(target=keepalive_sender, args=(conn, stop_keepalive, tag), daemon=True)
        sender.start()
    else:
        wire = zppcoder.wrap_wire_packet(RESPONSE_PAYLOAD)
        conn.sendall(wire)
        print(f"[{tag}] sent response ({len(wire)} bytes, payload={RESPONSE_PAYLOAD.hex()}):", flush=True)
        print(hexdump(wire), flush=True)
    try:
        while True:
            try:
                data = conn.recv(4096)
            except socket.timeout:
                continue  # short timeout is just for responsiveness, not a real idle-out
            except (ConnectionResetError, OSError):
                print(f"[{tag}] connection reset", flush=True)
                break
            if not data:
                print(f"[{tag}] client closed connection", flush=True)
                break
            all_bytes.extend(data)
            pending.extend(data)
            print(f"[{tag}] recv {len(data)} bytes:", flush=True)
            print(hexdump(data), flush=True)

            while True:
                payload, consumed = zppcoder.unwrap_wire_packet(bytes(pending))
                if consumed == 0:
                    break
                if payload is not None:
                    print(f"[{tag}] decoded packet ({len(payload)} bytes):", flush=True)
                    print(hexdump(payload), flush=True)
                else:
                    print(f"[{tag}] packet framed but failed ZPPCoder checksum "
                          f"({consumed} bytes) -- wrong key/table or corrupt data", flush=True)
                del pending[:consumed]
    finally:
        stop_keepalive.set()
        conn.close()
        if sender is not None:
            sender.join(timeout=2)
        if all_bytes:
            with open(binpath, "wb") as f:
                f.write(all_bytes)
            print(f"[{tag}] saved {len(all_bytes)} bytes to {binpath}", flush=True)


def listen_on(port: int):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(5)
    print(f"Listening on 0.0.0.0:{port}", flush=True)
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle_client, args=(conn, addr, port), daemon=True).start()


if __name__ == "__main__":
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    ports = tuple(int(p) for p in sys.argv[1:]) or PORTS
    threads = [threading.Thread(target=listen_on, args=(p,), daemon=True) for p in ports]
    for t in threads:
        t.start()
    print("Waiting for the game to connect... (Ctrl+C to stop)", flush=True)
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\nStopped.")
