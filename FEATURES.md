# Feature completion tracker

Status key:

- **Tested** — implemented and exercised by automated tests doing the real thing (on x86_64 Linux, no desktop session).
- **Needs VM** — implemented; tests cover TITAN's logic with the external tool or model stubbed. Not yet seen working on Ubuntu 24.04 ARM64 / GNOME.
- **Partial** — some of the requirement is built; the gap is stated.
- **Not built** — not started.

Nothing below has been run on the ARM64 Ubuntu VM, and the assistant has never been run against the live Claude API (no key in the build environment).

## 3. Desktop environment

| Feature | Status | Notes |
|---|---|---|
| Home dashboard, clock/date, system status, widgets (toggle per widget) | Tested | |
| Dock with running indicators, pinning, size | Tested | Calendar is date display only, no month view |
| Notifications panel and toasts | Tested | |
| Workspace switching (4 workspaces) | Tested | Shell windows; GNOME workspaces via `workspace.switch` need VM |
| Shell windows: open, focus, move, resize, minimize, maximize, close, shortcuts | Tested | |
| Managing other apps' windows (list, focus, minimize, maximize, close, move) | Needs VM | `wmctrl`/`xdotool`, Xorg only |
| Launcher: search, launch, categories, pin favourites, recents | Tested | Launching verified with a test `.desktop` entry |
| Files: browse, create folder, rename, move, copy, search, preview (text, images), storage, Trash | Tested | Downloads are in `~/Downloads`; no dedicated downloads view |
| Confirmation before permanent deletion and bulk operations | Tested | |
| Settings: theme, accent, wallpaper, dock, widgets, startup apps, shortcuts, notifications | Tested | |
| Settings: display, sound, network, Bluetooth, power status | Needs VM | Status read-outs; volume/mute and dark/light can be changed, the rest are read-only (Partial) |

## 4. AI core

| Feature | Status | Notes |
|---|---|---|
| Claude integration, tool selection and execution over 61 tools | Needs VM | Loop tested with a scripted model; never run against the real API |
| Plan mode (read-only tools) vs execute mode | Needs VM | Same caveat |
| Honest reporting: errors, denials and "awaiting approval" passed to the model | Tested | With scripted model |
| Conversation history, multiple conversations | Tested | |
| User-approved persistent memory injected into context | Tested | |
| Error recovery and progress events | Tested | Step limit, refusal, truncation, API errors |
| Context management for very long conversations | Partial | History is text-only replay; no compaction yet |

## 5. Computer control

| Feature | Status | Notes |
|---|---|---|
| Launch applications | Tested | |
| Switch/manage windows | Needs VM | |
| Keyboard, typing, mouse click, scroll (approval by default) | Needs VM | |
| Read accessible UI (AT-SPI) | Needs VM | No automated test at all; needs `python3-gi` |
| Permission system and approvals | Tested | |
| Interacting with websites (clicking, forms, tabs) | Not built | See ROADMAP |
| Multi-step workflows | Needs VM | Via the assistant |

## 6. Voice

| Feature | Status | Notes |
|---|---|---|
| Speech-to-text via whisper.cpp | Needs VM | Pipeline tested with stub binaries; `deploy/setup-voice.sh` untested |
| Text-to-speech (espeak-ng, piper, spd-say), voice and rate options | Needs VM | piper path has no test |
| Push-to-talk, voice commands, spoken replies | Needs VM | |
| Wake word and continuous conversation | Needs VM | Wake-phrase parsing tested; the listening loop has no automated test |
| Microphone status, voice settings | Tested | |

## 7. Browser

| Feature | Status | Notes |
|---|---|---|
| Open browser, navigate, web search | Tested | Via `xdg-open` (stubbed) |
| Read and summarise public pages, extract links | Tested | Fetch/extract tested against a local server; summarising needs the model |
| Bookmarks | Tested | |
| Downloads with permission, progress, notification | Tested | |
| Tab management | Not built | |
| Summarise PDFs/office documents | Not built | Text files only |

## 8. Terminal

| Feature | Status | Notes |
|---|---|---|
| Run commands, show output, timeouts, background runs with live output, cancel | Tested | |
| Risk classification and approval | Tested | 46 classifier cases |
| Process list and terminate (always asks) | Tested | |
| Explain errors | Needs VM | Hands the output to the assistant |
| Install approved packages | Partial | Through the terminal with approval; `sudo` cannot prompt for a password inside TITAN |

## 9. Memory

| Feature | Status | Notes |
|---|---|---|
| Preferences, project context, facts, reminders; search, update, delete, review, export | Tested | |
| Task history | Tested | Audit log and task list |
| Conversation summaries | Not built | Conversations are stored; no automatic summaries |

## 10. Security centre

| Feature | Status | Notes |
|---|---|---|
| Process monitor, listening ports and connections, permissions, audit log, file-permission checks, alerts | Tested | |
| Firewall, SSH, update status, login activity | Needs VM | Read-only checks; this build host has no ufw/sshd to verify against |
| Security notifications | Partial | Alerts show in the centre; not pushed as notifications |

## 11–13. Monitor, notifications, multitasking

| Feature | Status | Notes |
|---|---|---|
| Live CPU, per-core, RAM, disk, network rates, processes | Tested | |
| Battery, temperatures | Needs VM | Shown when the host exposes them |
| Notification categories, muting, reminders, task and download alerts | Tested | GNOME `notify-send` delivery needs VM |
| Background tasks, progress, cancellation, error reporting, file-lock conflicts | Tested | Queue is first-come; no priorities or resource limits |

## 14–16. Developer, plugins, personalisation

| Feature | Status | Notes |
|---|---|---|
| Project explorer, Git status/log/diff, virtualenv creation, run dev/build/test with live output | Tested | |
| Code editor integration | Partial | Opens your editor (`code`); no built-in editor |
| AI coding assistance | Needs VM | Via the assistant |
| Plugins: manifest, permissions, versions, error containment, enable/disable | Tested | In-process, not sandboxed |
| Themes, wallpapers, accent, dock, widgets, shortcuts, AI personality, voice, startup | Tested | |

## 17–20. Platform

| Feature | Status | Notes |
|---|---|---|
| Installer, systemd user service, launcher, autostart | Partial | Installer, launch, backup/restore, uninstall verified in a scratch home on x86_64; the systemd path and browser launcher need VM |
| Backup and restore | Tested | |
| Mac → VM sync (`deploy/sync-to-vm.sh`) | Needs VM | Syntax-checked only; no SSH target available |
| GNOME session integration beyond autostart | Not built | |
| Electron packaging | Not built | Deliberate, see ARCHITECTURE decision 9 |
| Performance testing | Not built | |
