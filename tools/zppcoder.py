"""Reimplementation of darkness.apk's ZPPCoder packet cipher.

Reverse-engineered from libcocos2dcpp.so (ZPPCoder::encode/decode/
encodeWithKey/decodeWithKey, ARM Thumb). The key and substitution table
were recovered by manually disassembling the PC-relative literal loads
("ldr rX, [pc, #N]" + "add rX, pc") and reading the resolved bytes
directly out of the binary. Validated with a round-trip encode->decode
self-test on random payloads -- see `_selftest()` at the bottom, and run
`python3 zppcoder.py` to check it still passes.

Wire format used by GameNet/ZPPTCPNetwork for every packet in both
directions:
    [2-byte big-endian length prefix = N][N bytes of ZPPCoder-encoded data]
where the encoded blob itself decodes to (N - 2) bytes of real payload
(the last 2 encoded-domain bytes are a random control byte + XOR checksum,
stripped during decode).

Algorithm (encode; decode mirrors it since XOR is self-inverse):
  1. Append a random control byte after the payload.
  2. Append an XOR checksum of (payload + control byte).
  3. XOR payload bytes with the control byte (chain step).
  4. XOR payload bytes with SBOX[running_sum], where running_sum starts at
     the control byte and accumulates KEY bytes (cycling every 16 bytes)
     one step per payload byte.
"""

import random

KEY = bytes.fromhex("bb1afefefec18410929a9a9ac37efb53")

SBOX = bytes.fromhex(
    "189e8bbe1698ffd7c12e90134253fbe1d66d251ebd0150eb68d999977cad354370bf00cd7aa6ceaa729fcafaaed38ebce30fd19226554eedb24c60e689cca56ea9b6c90b8723ac7744f9a05a4fb3a4d491f6072ba19a8374125fe93be08228dc0df57b7173c2b015b8b4583adbc6e72c7e3e14b541328a5e4d09f2465b803456386c8f3d10de5c458d22fe24c7a70603192df0af84ba815def375761daabc09c02cfc4111ffd08d26b3c4a54dd7d3fa3ee1766a2bb764794fc20b751392a1d3129f788218c2f676585f19bf8274869e44b30cb1ce5043393520c646a750ee89663490ad0f3b1c5d878a8c81ab98662951bec599d6fdfd5c305f4e279367fea40"
)

assert len(SBOX) == 256, f"sbox must be 256 bytes, got {len(SBOX)}"
assert sorted(SBOX) == list(range(256)), "sbox must be a permutation of 0..255"


def encode(payload: bytes, key: bytes = KEY, sbox: bytes = SBOX) -> bytes:
    """Encode a payload the way the client's sendDataWithZPPCoder does.

    Returns len(payload)+2 bytes. Caller must still prepend the 2-byte
    big-endian wire length prefix (= len(result)) before sending -- see
    wrap_wire_packet().
    """
    n = len(payload)
    buf = bytearray(payload) + bytearray(2)
    rnd = random.randint(0, 255)
    buf[n] = rnd
    checksum = 0
    for i in range(n + 1):
        checksum ^= buf[i]
    buf[n + 1] = checksum
    for i in range(n):
        buf[i] ^= buf[n]
    idx = rnd & 0xFF
    ki = 0
    for i in range(n):
        idx = (idx + key[ki]) & 0xFF
        ki = (ki + 1) % len(key)
        buf[i] ^= sbox[idx]
    return bytes(buf)


def decode(enc: bytes, key: bytes = KEY, sbox: bytes = SBOX):
    """Decode a ZPPCoder-encoded blob (the part after the 2-byte wire
    length prefix). Returns the original payload bytes, or None if the
    checksum doesn't validate (wrong key/table, corrupt data, or not a
    ZPPCoder packet at all).
    """
    total = len(enc)
    if total < 2:
        return None
    n = total - 2
    buf = bytearray(enc)
    seed = buf[n]
    idx = seed & 0xFF
    ki = 0
    for i in range(n):
        idx = (idx + key[ki]) & 0xFF
        ki = (ki + 1) % len(key)
        buf[i] ^= sbox[idx]
    for i in range(n - 1, -1, -1):
        buf[i] ^= buf[n]
    checksum = 0
    for i in range(n + 1):
        checksum ^= buf[i]
    if checksum != buf[total - 1]:
        return None
    return bytes(buf[:n])


def unwrap_wire_packet(raw: bytes):
    """Given raw bytes read off the socket, split off the 2-byte length
    prefix and decode the rest. Returns (payload, consumed_bytes); payload
    is None if there isn't a full packet yet or it fails to decode.
    """
    if len(raw) < 2:
        return None, 0
    length = (raw[0] << 8) | raw[1]
    if len(raw) < 2 + length:
        return None, 0  # incomplete, wait for more bytes
    payload = decode(raw[2:2 + length])
    return payload, 2 + length


def wrap_wire_packet(payload: bytes) -> bytes:
    """Encode a payload and prepend the wire length prefix, ready to send."""
    enc = encode(payload)
    return bytes([(len(enc) >> 8) & 0xFF, len(enc) & 0xFF]) + enc


def _selftest():
    for _ in range(1000):
        n = random.randint(1, 64)
        payload = bytes(random.randint(0, 255) for _ in range(n))
        wire = wrap_wire_packet(payload)
        decoded, consumed = unwrap_wire_packet(wire)
        assert consumed == len(wire), (consumed, len(wire))
        assert decoded == payload, (payload, decoded)
    print("zppcoder self-test OK (1000 random payloads)")


if __name__ == "__main__":
    _selftest()
