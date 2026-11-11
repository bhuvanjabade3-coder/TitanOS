# TITAN OS

An AI-first desktop environment for Ubuntu 24.04 (GNOME on Xorg). You tell TITAN
what you want; it plans, carries out the actions it is permitted to, asks before
anything risky, and reports what actually happened.

TITAN is two programs:

- **TITAN Core** (`backend/`): a local Python service that owns every capability
  (files, terminal, apps, windows, browser, memory, voice, plugins) behind one
  permission-checked action registry, and runs the Claude tool loop.
- **TITAN Shell** (`frontend/`): the desktop UI — windows, dock, launcher,
  workspaces and twelve built-in apps — talking to Core over HTTP and WebSocket.

See [FEATURES.md](FEATURES.md) for exactly what is built, what is tested, and
what still needs verifying on a real Ubuntu desktop.

## Install on the Ubuntu target

```bash
sudo apt install python3 python3-venv nodejs npm curl
```

```bash
deploy/install.sh --autostart
```

The installer is user-level (no sudo), prints any optional packages that are
missing, installs a systemd user service, and adds TITAN to the app grid. Then
put your key in `~/.config/titan/env` (`ANTHROPIC_API_KEY=...`, file mode 600)
and restart the service:

```bash
systemctl --user restart titan-core
```

From the Mac, `deploy/sync-to-vm.sh user@vm --install` copies the repo over SSH
and runs the installer there. Nothing is ever installed on the Mac.

## Develop

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]' && .venv/bin/titan-core
```

```bash
cd frontend && npm install && npm run dev
```

Open http://127.0.0.1:5173. Tests: see [TESTING.md](TESTING.md).

## Documents

| File | Contents |
|---|---|
| [FEATURES.md](FEATURES.md) | Feature completion tracker with verification status |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Design and every architectural decision |
| [SECURITY.md](SECURITY.md) | Threat model, permission system, known limits |
| [TESTING.md](TESTING.md) | How to run each test suite and what it covers |
| [ROADMAP.md](ROADMAP.md) | What is left, in order |
| [CHANGELOG.md](CHANGELOG.md) | Release notes |
| [docs/PLUGINS.md](docs/PLUGINS.md) | Writing plugins |
