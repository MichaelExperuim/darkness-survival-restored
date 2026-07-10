# Darkness Survival — Restored

A patched, fully-playable build of **Darkness Survival** (Zero++ Software,
2016), a mobile dungeon-crawler RPG whose online backend has been dead for
years. This restoration removes every dependency on that backend — the
game now runs entirely offline, standalone, no server required.

## What was wrong

The original game refused to start with "Connecting to the Server,"
displayed forever, because it phones home to a custom game server
(`rpg1.dungeonheroine.cafe24.com`) that no longer exists. A Google Play
Games Services sign-in prompt (also now defunct) blocked progress even
after bypassing the first screen. And once past the title screen, the
in-game UI (inventory, menus, everything) was completely unresponsive to
touch, because the game was still silently retrying the dead connection
every single frame in the background, and its own "connection failed"
popup was eating every tap before it could reach the actual game.

## What this build changes

1. **Removed the network gate.** The function that shows "Connecting to
   the Server" and blocks the title screen has been patched to do
   nothing, so the game proceeds straight to gameplay without ever
   needing a server.
2. **Disabled Google Sign-In.** Both the button-triggered and
   automatic-on-launch sign-in paths are neutralized. The game never
   attempts to contact Google Play Games Services.
3. **Fixed unresponsive in-game UI.** The per-frame network status check
   that was silently reopening a "connection failed" popup — and eating
   all touch input in the process — every single frame is patched out,
   so gameplay UI is fully responsive.
4. **No gameplay content was altered.** Every patch is a targeted
   bypass of dead online infrastructure — items, combat, dungeon
   generation, and story content are all untouched, original 2016
   assets.

See `PATCH_NOTES.md` for a plain-language explanation of each fix, or
`TECHNICAL_WRITEUP.md` for the full reverse-engineering story, including
a completely-solved custom network protocol and a real memory-safety bug
found and fixed along the way. Screenshots of the working game are in
`screenshots/`.

## Installing

See `INSTALL_GUIDE.md` for full step-by-step instructions with
troubleshooting. Quick version:

1. Copy `darkness_survival_restored.apk` to your Android device.
2. Tap it to install (you'll likely need to allow "install unknown
   apps" for whichever app you're installing through — Android will
   prompt you for this automatically).
3. If you still have the original `darkness.apk` installed, uninstall it
   first — this build is signed with a different key, so Android will
   refuse to install over it directly.
4. Launch **Darkness Survival**. It should go straight to the title
   screen and "Tap screen to start." should be immediately responsive —
   no waiting, no connecting. Tap to start, and gameplay UI (movement,
   inventory, menus) should be fully responsive throughout.

This exact flow (transfer APK → tap to install → play) has been tested
end-to-end on physical hardware.

## Known limitations

- This restores **offline single-player functionality only**. Any
  originally-online features (leaderboards, cloud save, Play Games
  achievements) are gone, because the services behind them are gone.
- Save data is local to the device only (no cloud backup) — this was
  already largely true even when the servers were alive, since this is a
  single-player dungeon crawler.
- Tested on a physical Android device (arm64, Android 9). Should work on
  any real ARM Android device; emulators may need an ARM-translation
  capable image (see `TECHNICAL_WRITEUP.md` for what we learned about
  that the hard way).

## Credits

Original game: Zero++ Software, 2016. This is an unofficial community
restoration patch for personal/preservation use, not a re-release —
all original game assets and code remain the property of their
original creators.

Reverse-engineering, patching, and testing performed using
[Claude Code](https://claude.com/claude-code), Anthropic's agentic
coding CLI. See `PATCH_NOTES.md` for full credits.
# darkness-survival-restored
