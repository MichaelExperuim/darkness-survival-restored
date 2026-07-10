# Developer tools

These aren't needed to play the restored game — see the main
`README.md` and just install the APK. These are for anyone who wants to
go further and attempt a real (fan-made) backend server for online
features, using the fully-reverse-engineered protocol described in
`TECHNICAL_WRITEUP.md`.

- **`zppcoder.py`** — standalone, validated implementation of the game's
  packet cipher. `encode()`/`decode()` for raw payloads,
  `wrap_wire_packet()`/`unwrap_wire_packet()` for the full wire format
  including the 2-byte length prefix. Run `python3 zppcoder.py` to
  re-verify the self-test (1000 random round-trips) still passes.

- **`tcp_probe.py`** — a raw TCP listener for ports 4776 (login) and
  4778 (game server) that auto-decodes any packet the client sends using
  `zppcoder.py`, and can send crafted responses back. Requires
  `zppcoder.py` in the same directory. Usage: `python3 tcp_probe.py`.

- **`dnsmasq-darkness.conf`** — redirects only
  `rpg1.dungeonheroine.cafe24.com` to a machine of your choosing,
  forwarding everything else upstream so a test device keeps normal
  internet access. An alternative to `adb reverse` for setups where the
  test device isn't on USB (e.g. testing over WiFi). Update the IP
  address inside before use.

Note: this published APK already bypasses the network layer entirely
(see `TECHNICAL_WRITEUP.md`), so these tools are only relevant if you
want to go a different direction and restore real online functionality
instead of just single-player offline play.
