# Install Guide

Tested end-to-end on a physical Android device using this exact process.

## 1. Get the APK onto your device

Copy `darkness_survival_restored.apk` to your Android device however is
convenient — USB transfer, cloud storage, email attachment, etc. If your
device already has it (e.g. you downloaded this zip directly on the
device), just find it in your **Downloads** app or file manager.

## 2. Install it

1. Open your **Files** / **Downloads** app and tap
   `darkness_survival_restored.apk`.
2. Android will likely show a prompt like **"For your security, your
   phone is not allowed to install unknown apps from this source."**
   This is normal for any APK installed outside the Play Store. Tap
   **Settings** on that prompt, enable **Allow from this source** for
   the app you're installing through (Files, Chrome, etc.), then go
   back and tap the APK again.
3. Tap **Install**.
4. If you still have the *original* `darkness.apk` installed, Android
   will refuse to install over it and show an error instead of the
   normal install prompt — this restored build is signed with a
   different key than the original. Uninstall the old copy first
   (Settings → Apps → Darkness Survival → Uninstall), then retry step 3.
5. Once installed, tap **Open** (or find **Darkness Survival** in your
   app drawer).

## 3. Play

- The title screen should appear immediately — no "Connecting to the
  Server," no waiting.
- Tap anywhere to start.
- Movement, inventory, menus, and all other UI should respond normally
  to touch throughout gameplay.

## Troubleshooting

**"App not installed" error.** Almost always means an existing copy
(original or a previous restored build) with a different signature is
already on the device. Uninstall it first, then reinstall.

**Stuck on a black screen after tapping install.** Give it a few
seconds — first launch on some devices takes a moment to initialize
graphics. If it's still black after ~15 seconds, force-close and relaunch.

**Something else looks broken.** This restoration patches out dead
online infrastructure only — see `PATCH_NOTES.md` for exactly what was
changed, and `TECHNICAL_WRITEUP.md` if you want the full
reverse-engineering details behind each fix.

## Requirements

- Android device with an ARM processor (virtually all real Android
  phones/tablets — this will not run correctly on most x86 emulators
  without ARM translation support; see `TECHNICAL_WRITEUP.md` if you
  want to attempt emulator testing anyway).
- No internet connection required to play.
