# Patch Notes — Darkness Survival Restoration

**Version:** Unofficial restoration patch, based on original v1.1.29
**Original game:** Darkness Survival, Zero++ Software, 2016
**Status:** Fully playable offline, tested end-to-end on physical
Android hardware including a real "download and install" flow.

---

## The problem

Darkness Survival is a single-player dungeon-crawler RPG that, despite
having no online multiplayer, was built with an always-required
connection to a now-dead backend server. With that server gone, the
game was completely unplayable: it would hang forever on "Connecting to
the Server" and never let you past the title screen.

## What was actually happening

The game's title screen and in-game systems both depend on a custom
network protocol (not the kind of thing you can just point at a working
replacement — it's a fully custom encrypted TCP protocol the original
developers wrote themselves). That backend's domain still exists in DNS,
but nothing has been listening on it for a long time. On top of that,
the game also tries to sign in to Google Play Games Services on every
launch, which is a second, independent dead dependency.

Three distinct issues had to be found and fixed:

### 1. The title screen would never load

**Cause:** the game shows a "Connecting to the Server" message and
blocks progress while it waits for a response from the dead backend,
which never arrives.

**Fix:** patched out the function responsible for showing that message
and initiating the connection attempt, so the title screen loads and
responds to taps immediately.

### 2. A Google sign-in prompt blocked progress

**Cause:** separately from the game's own server, it also tries to sign
in to Google Play Games Services automatically on every launch. That
integration is also defunct (it depends on the original developer's own
Google account/project configuration, which no longer exists in a
working state for this app).

**Fix:** disabled both the automatic sign-in attempt and the
manually-triggered sign-in button, so the game never tries to reach
Google's services at all.

### 3. In-game UI was completely unresponsive

This was the trickiest one, and only became visible after fixing #1 and
#2 — you'd tap to start, get into the actual game world, and then
nothing would respond to touch at all: no inventory, no menus, nothing.

**Cause:** even with the title-screen blocker removed, the game was
still quietly trying to reconnect to its dead server in the background,
once per rendered frame. Every single frame, it would notice the
connection wasn't there, silently open a "connection failed" popup, and
close it again — and that popup, even though it wasn't visibly staying
on screen, was still intercepting every touch input meant for the
actual game underneath it. Sixty times a second, forever.

**Fix:** patched the specific function that checks connection status so
it always reports "no problem here," which stops the invisible
popup-storm at its source. Gameplay UI is fully responsive.

## What was *not* changed

No gameplay content was touched. Items, combat, dungeon layouts, enemy
behavior, story text, art, and audio are all completely original and
unmodified. Every change in this patch is narrowly scoped to bypassing
dead online infrastructure — nothing about how the game actually plays
was altered.

## Known limitations

- This is an **offline-only** restoration. Any features that
  specifically required the live server or Google Play Games (if any
  ever existed beyond sign-in) are not restored — they can't be,
  because the services behind them no longer exist.
- Save data lives on-device only; there was never a cloud save system
  to restore even if the backend were alive.

---

## Credits

**Original game** — Darkness Survival, © Zero++ Software, 2016. This is
an unofficial, non-commercial preservation patch for personal use. All
original assets, code, and design remain the property of their
original creators; nothing about the core game is redistributed or
claimed here beyond what's needed to apply these fixes.

**Restoration work** — reverse-engineering, patching, and testing for
this release was performed using **[Claude Code](https://claude.com/claude-code)**,
Anthropic's agentic coding CLI, working interactively with the user
across disassembly, live dynamic instrumentation, and iterative testing
on real hardware to diagnose and fix each of the three issues above.
