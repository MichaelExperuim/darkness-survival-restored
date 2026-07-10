# Restoring Darkness Survival: A Full Technical Writeup

This is the complete account of reverse-engineering and patching
**Darkness Survival** (Zero++ Software, 2016) back into a playable state
after its backend went dark. Everything here was found through binary
disassembly, live dynamic instrumentation, and a lot of empirical
testing against the actual running app — not guesswork.

## The symptom

The game boots, shows its title screen, and displays "Connecting to the
Server" forever. "Tap screen to start." is visible but unresponsive. This
happens even with full internet connectivity.

## Root cause #1: the backend is dead

The app is built on Cocos2d-x, with essentially all game logic compiled
into a single native library, `lib/armeabi/libcocos2dcpp.so` (ARMv7,
~11.8 MB). Disassembling the connection-setup code
(`GameNet::connectLoginServer()` / `GameNet::connectGameServer()`)
revealed the exact endpoints, traced by hand through the ARM Thumb
PC-relative literal pool (not inferred from strings or convention):

- Login server: `rpg1.dungeonheroine.cafe24.com:4776`
- Game server: `rpg1.dungeonheroine.cafe24.com:4778`

The hostname's DNS record still resolves, but nothing listens on either
port. The game isn't using HTTP — it's a fully custom raw TCP protocol
(a class called `ZPPTCPNetwork`), which is also why an earlier attempt to
intercept traffic with a standard HTTPS proxy (Burp + Frida SSL-pinning
bypass) caught nothing: there's no TLS or HTTP here at all.

## Reverse-engineering the wire protocol

Every packet, in both directions, follows this framing:

```
[2-byte big-endian length prefix = N][N bytes of ZPPCoder-encoded data]
```

The encoded blob decodes to `N-2` bytes of real payload; the last two
encoded bytes are a random control byte and an XOR checksum, stripped on
decode.

### The `ZPPCoder` cipher — fully solved

A custom XOR/substitution stream cipher wraps every packet. By manually
disassembling `ZPPCoder::encode`/`decode`/`encodeWithKey`/`decodeWithKey`
and resolving the ARM Thumb PC-relative literal loads (`ldr rX, [pc, #N]`
+ `add rX, pc`), the embedded 16-byte XOR key and 256-byte substitution
table were extracted directly from the binary and reimplemented in
Python. The reimplementation was validated with a 1000-trial random
round-trip test (encode → decode reproduces the original bytes exactly,
every time) — this is a working, tested implementation, not a
best-effort guess.

Algorithm:
1. Append a random control byte after the payload.
2. Append an XOR checksum of (payload + control byte).
3. XOR payload bytes with the control byte.
4. XOR payload bytes with `SBOX[running_key_sum]`, where the running sum
   cycles through the 16-byte key, one step per payload byte.

### Packet semantics

`GameNet::getPacketType()` reads byte 0 of the decoded payload directly
(confirmed: that getter reads offset `0x200c` into the `GameNet` object,
exactly `0xc + 0x2000` — right after the 8192-byte outgoing packet
buffer). Valid types are 1–42; anything outside that range hits an
"unrecognized packet" fallback.

`GameNet::getResult()` reads byte 1. Tracing the actual handler for
packet type 1 in `UILayer::networking()` showed that `result == 0` or
`result == 2` both take a "success" branch (sync server time, dispatch a
success event), while `result == 2` specifically triggers additional
processing that `result == 0` skips.

### A real bug in the original binary

Faking a server response and observing the client's behavior surfaced a
genuine memory-safety bug: after a certain idle/reconnect timing,
`ZPPTCPNetwork::disconnectServer()` calls `pthread_mutex_lock()` on a
mutex embedded in an already-destroyed connection object. Android's
FORTIFY hardening catches this and aborts the process with `SIGABRT`:

```
Abort message: 'FORTIFY: pthread_mutex_lock called on a destroyed mutex'
  ZPPTCPNetwork::disconnectServer()
  ZPPTCPNetwork::disconnectServer(ZPPTCPNetwork*)
  GameNet::disconnect()
  UILayer::networking()
```

This almost certainly never manifested against the real, live server —
a real server responds fast enough that the client never hits the exact
"connected, then nothing happens" timing window that triggers it. It's a
latent bug the original developers likely never encountered. It's not
what we ultimately patched around (see below), but understanding it was
essential to correctly diagnosing everything else.

## Building test infrastructure

To observe and interact with the game's networking without a real
server, this project built:

- `zppcoder.py` — the validated cipher implementation (encode/decode +
  full wire-format helpers).
- `tcp_probe.py` — a raw TCP listener for ports 4776/4778 that
  auto-decodes any packet the client sends and can send crafted
  responses back.
- A hostname patch (`rpg1.dungeonheroine.cafe24.com` → `127.0.0.1`,
  written directly into the native library's string table, padded with
  nulls to preserve the exact original byte layout) combined with
  `adb reverse` port tunneling, so the game running on a real phone
  would connect straight to a listener on the development machine over
  USB — no DNS tricks, no root required.

This let us watch real login packets arrive and decrypt them live,
confirming the whole protocol reconstruction was correct.

## Removing Google Sign-In

A "This app requires the latest Google Play Games" prompt turned out to
be entirely separate from the custom protocol above — it's Google Play
Games Services (GPGS), a standard library integration
(`com.zeroplusplus.common.GameHelper`/`BaseGameActivity`, a well-known
open-source Google sample pattern). Its backend is defunct for this app
too, since it depends on the original developer's now-inactive Google
Play Console project.

Two independent trigger points were found and neutralized in smali:

1. **`NativeWrapperActivity.login()`** — a JNI-callable method that only
   called `beginUserInitiatedSignIn()`. Patched to an unconditional
   `return-void`.
2. **`GameHelper.onStart()`** — called automatically on every activity
   start (via `BaseGameActivity.onStart()`), attempts a *silent*
   reconnect if `mConnectOnStart` is true. Patched the conditional branch
   into an unconditional jump to the existing "not connecting, report
   failure gracefully" path that was already in the original code for
   this exact scenario — so no new code paths were introduced, just an
   existing one made unconditional.

## The final blocker: finding what actually shows "Connecting to the Server"

With the network dead and Sign-In removed, the game still hung on
"Connecting to the Server" forever, and tapping the screen did nothing.
Static analysis repeatedly pointed at the wrong code (a popup class that
looked sprite-only on first read, a title-screen class with no
networking code at all) — the kind of dead end that's very easy to sink
unlimited time into via pure disassembly.

The breakthrough was switching to **live dynamic instrumentation** with
Frida. Since the target device wasn't rooted (`su` unavailable, a locked
`user`-type build), the standard `frida-server` approach was unavailable.
Instead, **`frida-gadget`** — a shared library that runs inside the
target app's own process, requiring no root — was embedded directly into
the APK:

1. Downloaded the ARM32 gadget build matching the installed `frida`
   client version.
2. Added it as `lib/armeabi/libfrida-gadget.so`, loaded via one injected
   smali line (`System.loadLibrary("frida-gadget")`) right before the
   game's own native library load in `Cocos2dxActivity`.
3. Added a `libfrida-gadget.config.so` JSON config with
   `"on_load": "wait"`, so the app pauses at startup until a Frida client
   explicitly connects and resumes it — avoiding a race where the app's
   init finishes before instrumentation attaches.

With hooks on `cocos2d::Label::setString`/`cocos2d::ui::Text::setString`
filtering for the string "Connecting", the *exact* moment the label gets
created was caught, with a full native backtrace:

```
Cocos2dxRenderer_nativeInit → Application::run()
  → AppDelegate::applicationDidFinishLaunching()
    → GameScene::getInstance() → UILayer::signIn()
      → UILayer::sendPacket() → UILayer::openConnectingServer()
        → UIConnectingServer::init() → Label::createWithTTF(...)
```

This resolved everything at once: `UILayer::signIn()` calls
`GameNet::prepareSignIn()` then `sendPacket()`, automatically, once, at
app startup — well before the title screen even renders. The same live
session also confirmed, definitively, that tapping the screen triggers
**zero** related function calls — the tap handler and the dead sign-in
flow aren't even connected at the code level.

## The fix

`UILayer::openConnectingServer()` was patched with a minimal 2-byte
change: its first instruction was replaced with `bx lr` (immediate
return), a valid ARM Thumb instruction encoding (`0x4770`). Since this
executes before the function pushes any registers, it's a perfectly
safe no-op — every instruction after it in the function becomes
unreachable dead code, harmless bytes that are never executed.

This prevents the "Connecting to the Server" popup/label from ever being
created, and — as it turned out — also freed up whatever was capturing
touch input on top of "Tap screen to start.", since that promptly began
responding to taps immediately after this patch.

## Second blocker: in-game UI became unresponsive

The title screen fix wasn't the whole story. Getting into actual
gameplay revealed a second, related problem: none of the in-game UI
(inventory, menu icons, anything) responded to touch, even though the
very first tap (title screen → gameplay) had worked.

The cause was the other half of the same mechanism. Patching
`openConnectingServer()` only silenced the *visual* popup — it didn't
stop `UILayer::sendPacket()` from still calling
`GameNet::connectGameServer()` in the background every time it's
invoked, nor did it stop `UILayer::networking()` (which runs every
single frame, confirmed via live Frida hooks at a genuine 60fps) from
polling the result.

Re-examining that per-frame poll: `GameNet::getNetworkStatus()` resets
its cached status to "connected, nothing new" at the top of every call,
and with no real server ever responding, it never reaches the "packet
ready" state. `UILayer::networking()`'s logic is:

```
status = GameNet::getNetworkStatus()
if (status != -5) {                 // "packet ready"; never true with no server
    UIMessageBox::create(...)        // "connection failed" popup
    PopupManager::openPopup(...)
    GameNet::disconnect()
}
```

With no server, this branch runs **every frame**, repeatedly
constructing and opening a modal failure popup. Modal popups in
Cocos2d-x intercept touch input for everything beneath them — so even
though the popup wasn't visibly rendering persistently (recreated too
fast per-frame to show, or rendering off in a state that never became
visible), it was almost certainly still consuming every touch event
meant for the actual game UI underneath it.

### The fix

Confirmed `GameNet::getNetworkStatus()` has exactly one caller in the
entire binary — this exact call site in `UILayer::networking()` — so it
was safe to patch in isolation with no other side effects. It was
replaced with a 6-byte stub that unconditionally returns `-5` ("packet
ready") and nothing else:

```
movs r0, #5      ; 05 20
rsbs r0, r0, #0  ; 40 42   (r0 = -5)
bx lr            ; 70 47
```

This permanently skips the failure-popup branch. The subsequent
packet-type dispatch (`GameNet::getPacketType()`, reading byte 0 of a
buffer that's never actually populated since no real packet ever
arrives) reads `0`, which is outside the valid 1–42 range and falls
through to a harmless no-op path — confirmed safe, not the crash-prone
`disconnect()` path, since that only lives inside the individual
per-type success handlers, not the generic "unrecognized type"
fallback.

## Verifying the fix

Tested with zero companion infrastructure running — no `tcp_probe.py`,
no `adb reverse`, no port forwarding of any kind. Fresh install, cold
launch: title screen appears immediately with "Tap screen to start."
fully responsive, tapping transitions straight into gameplay ("You've
moved to B1F.", full HUD, tutorial hints, movement working). With the
`getNetworkStatus()` patch added, in-game UI (inventory, menus, all
touch targets) is confirmed fully responsive as well, tested directly
in actual gameplay on physical hardware.

## Summary of all binary patches

| Target | File | Change |
|---|---|---|
| Hostname string | `libcocos2dcpp.so` | `rpg1.dungeonheroine.cafe24.com` → `127.0.0.1` (null-padded, same length) — vestigial at this point given the patches below, kept for defense-in-depth |
| `NativeWrapperActivity.login()` | smali | Body replaced with `return-void` |
| `GameHelper.onStart()` | smali | `if-eqz v0, :cond_1` → unconditional `goto :cond_1` |
| `UILayer::openConnectingServer()` | `libcocos2dcpp.so` | First instruction replaced with `bx lr` (2 bytes: `70 47`) |
| `GameNet::getNetworkStatus()` | `libcocos2dcpp.so` | Replaced with a 6-byte stub that always returns `-5` ("packet ready"), skipping the per-frame "connection failed" popup that was eating all in-game touch input |

All patches were applied to `smali`/native code, rebuilt with `apktool`,
zip-aligned, and signed with a debug key (`apksigner`) before install.

## Tools included

See `tools/` for the developer-facing scripts built during this
investigation — useful if anyone wants to attempt reconstructing a real
(fan-made) backend server for online features, rather than just
bypassing them:

- `zppcoder.py` — the cipher implementation.
- `tcp_probe.py` — raw TCP capture/response listener for the game's
  protocol.
- `dnsmasq-darkness.conf` — a DNS redirect config, an alternative to
  `adb reverse` for non-USB testing setups.
