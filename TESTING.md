# Testing

| Suite | Command | What it covers |
|---|---|---|
| Backend | `cd backend && .venv/bin/pytest -q` | Risk classifier, file confinement, approvals, policy, terminal, tasks, notifications, memory, apps, window/input command construction, browser, security overview, dev tools, plugins, voice plumbing, AI loop, HTTP/WS routes |
| Frontend unit | `cd frontend && npm test` | Formatting helpers, gauge component |
| Type-check + build | `cd frontend && npm run build` | Whole shell compiles |
| End-to-end | `cd frontend && npm run e2e` | Real browser against a real, throwaway Core: launcher, files, approvals (deny and approve), terminal, window management, workspaces, assistant error path, memory, security centre, settings persistence, notifications |

The end-to-end runner creates a scratch home and data directory, so it never
touches your files. It needs Playwright's Chromium (`npx playwright install chromium`).

## What the tests do not prove

Be precise about this when reading a green run:

- **External tools are stubbed.** `wmctrl`, `xdotool`, `xdg-open`, `arecord`,
  `whisper-cli` and `espeak-ng` are replaced by fake executables. The tests prove
  TITAN builds the right commands and handles their output and absence; they do
  not prove real windows move or real audio is transcribed.
- **The model is stubbed.** AI tests use a scripted client. They prove the loop,
  gating and honest reporting; no test calls the real Claude API.
- **No ARM64 or GNOME run.** Everything so far ran on x86_64 Linux without a
  desktop session.

## Verifying on the Ubuntu VM (not yet done)

1. `deploy/install.sh`, then `systemctl --user status titan-core`.
2. `cd backend && .venv/bin/pip install -e '.[dev]' && .venv/bin/pytest -q`
3. `cd frontend && npx playwright install chromium && npm run e2e`
4. Manual checks in an Xorg session: launch an app from the launcher; in the
   assistant "open Firefox", "list my windows", "create a folder called Projects";
   Settings → Voice after `deploy/setup-voice.sh`; `deploy/backup.sh` and restore.

Record results in FEATURES.md by changing "needs VM" entries to "verified".
