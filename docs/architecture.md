# TITAN OS — Architecture & Roadmap (v0, approved 2026-11-11)

## Context
We're building TITAN OS: an AI-first desktop layer for Ubuntu ARM64, controlled with natural language and voice through Claude. Development happens on a MacBook Air (Apple Silicon) and the code runs in a UTM VM. This document covers environment findings, architecture, limitations and a phased roadmap. **Nothing has been implemented or configured yet.**

Decisions confirmed with you:
- **Shell mode:** fullscreen Electron app on stock Ubuntu 24.04 GNOME, using the X11 session. A dedicated TITAN login session (minimal X11 window manager) comes later.
- **Voice:** local whisper.cpp in the VM.
- **Dev loop:** edit on the Mac, rsync over SSH, run and test in the VM.

---

## 1. Environment findings (read-only inspection)

| Item | Finding |
|---|---|
| Host | macOS 27.0, arm64, 10 cores, 16 GB RAM |
| Project dir | `/Users/bhuvanjabade/TITAN-OS`: **empty**, not a git repo |
| Python | 3.14.5 (python.org framework build), pip 26.1 |
| Node | v24.18.0, npm 11.16 (no pnpm, yarn, tsc or electron installed globally, which is fine because these are per-project) |
| Other | git 2.54, Homebrew 7.0, sqlite3 3.54, openrsync, VS Code, Cursor |
| Missing | uv, docker (neither required) |
| UTM | Installed. `utmctl` is at `/Applications/UTM.app/Contents/MacOS/utmctl`. One VM, **"Linux" (started)**, UUID 79DEC25D-… |
| VM access | No SSH host or known_hosts entry yet, so I can't inspect inside the VM |
| API key | No `ANTHROPIC_API_KEY` in the environment, which is fine; it will be stored in the VM, not on the Mac |

**Mismatch to handle:** Ubuntu 24.04 ships Python 3.12, while the Mac has 3.14. The backend will **target Python 3.12** and use a venv in the VM. On the Mac we only run unit tests that don't depend on the platform.

---

## 2. Dev (macOS) → deploy (Ubuntu ARM64) workflow

```
Mac (edit, git, unit tests, UI hot-reload)
  │  scripts/sync.sh   → rsync -az --delete-excluded (excludes node_modules, .venv, data/) to titan@vm:~/titan-os
  │  scripts/vm.sh     → ssh helpers: run backend, run tests, tail logs
  │  ssh -L 8765:localhost:8765   → Mac browser/Vite can talk to the real VM backend
  ▼
Ubuntu VM (real runtime: titand Python backend + Electron shell, X11 session)
```

- **Fast UI iteration:** run Vite on the Mac and point it at the VM backend through an SSH tunnel. The UI then works against real Linux data, not mocks.
- **Full runs:** `npm run build` happens in the VM, because Electron must be the linux-arm64 build. Then the Electron shell is launched on the VM display.
- **Platform adapters:** Linux-only services (windows, `.desktop` apps, audio) return a clear `unsupported_platform` error on macOS. They never return fake data.
- **One-time VM setup, done only after your approval, with every command shown first:** openssh-server, build-essential, cmake, python3-venv, Node 24 LTS (via nvm, user-level, no system changes), wmctrl, xdotool, portaudio19-dev, libsecret, and selecting "Ubuntu on Xorg" at login.

---

## 3. Architecture

### 3.1 Process model
```
┌──────────────── Electron shell (titan-shell, Node/TS) ────────────────┐
│ main: fullscreen BrowserWindow, spawns/monitors titand, global hotkey │
│ preload: contextIsolation, narrow typed bridge (no nodeIntegration)   │
│ renderer: React + TS UI (titan-ui)                                    │
└───────────────┬───────────────────────────────────────────────────────┘
                │ WebSocket ws://127.0.0.1:8765  (JSON-RPC 2.0 + event stream)
                │ auth: random per-launch token passed via env → preload
┌───────────────▼──────────── titand (Python 3.12, FastAPI + uvicorn) ──┐
│ Core: RPC router · event bus · config · logging · SQLite (WAL)        │
│ Services (each a module with a typed interface + tests):              │
│  agent     Claude tool-use loop, streaming, planning, cancellation    │
│  tools     registry: schema, risk level, executor → wraps services    │
│  perms     policy engine, approval requests, audit log                │
│  fs        list/read/search/move/copy/trash (gio trash, never rm)     │
│  apps      XDG .desktop discovery + launch (gtk-launch / Gio)         │
│  terminal  PTY sessions (ptyprocess) ↔ xterm.js                       │
│  windows   list/focus/move/close via EWMH (python-xlib / wmctrl)      │
│  browser   open URLs (xdg-open); automation via Playwright Chromium   │
│  sysmon    psutil: CPU/mem/disk/net/procs/temps, pushed every 1s      │
│  memory    conversations, facts, preferences; SQLite FTS5 search     │
│  voice     mic capture → VAD → whisper.cpp → text; optional TTS       │
│  secrets   API key via libsecret (keyring), fallback 0600 file        │
└───────────────────────────────────────────────────────────────────────┘
```

**Why the backend owns everything privileged:** Claude's tool calls run only in titand, behind `perms`. The renderer can't reach the OS directly. The API key never leaves titand.

### 3.2 Agent and automation design
- The Python `anthropic` SDK runs a manual tool-use loop, so every tool call passes through `perms` before it executes. Responses stream to the UI as events: `agent.delta`, `agent.tool_request`, `agent.tool_result`, `agent.done`.
- **Models:** a fast model (Sonnet or Haiku class) for quick commands and a stronger model (Opus class) for multi-step plans. Exact model IDs and params will be checked against the current Claude API reference at implementation time, and both are configurable.
- **Multi-step automation:** Claude proposes a plan, the UI shows it as a checklist, and steps run one by one with live status. You can pause or cancel at any time. Each step is a tool call, so every step gets a permission check.
- **Context:** system prompt + relevant memories (FTS5 retrieval) + a short system snapshot (open windows, cwd, time). Prompt caching on the static system or tools prefix.

### 3.3 Security and permission centre
- **Risk tiers per tool:**
  - `read`: auto-allowed. Examples: list files, sysmon, list windows.
  - `write`: ask once per scope, with a "remember for this folder/app" option. Examples: create or move files, launch apps, type into windows.
  - `destructive`: **always ask**, showing exactly what will happen. Examples: trash files, kill processes, close windows, arbitrary shell commands.
  - `forbidden`: never run. Examples: sudo/pkexec, writes outside `$HOME`, `~/.ssh`, `~/.gnupg`, the keyring, TITAN's own secrets.
- Shell commands proposed by Claude are shown verbatim and run in a PTY you can watch. No hidden execution.
- Deletes always go to Trash.
- Every tool call, decision and result is written to an append-only `audit_log` table, viewable in the Security centre.
- Prompt-injection hygiene: tool results from files or web pages are marked as untrusted content in the prompt, and never raise permissions.

### 3.4 Data (SQLite, `~/.local/share/titan/titan.db`)
Tables: `conversations`, `messages`, `memories` (+ FTS5), `preferences`, `permission_grants`, `audit_log`, `automation_runs`, `automation_steps`, `settings`. Migrations are versioned SQL files applied at startup.

### 3.5 Frontend (React 19 + TypeScript + Vite)
- **Desktop:** charcoal `#0E0F13` base with electric purple `#8B5CF6` and blue `#3B82F6` accents. Glass panels, Framer Motion transitions.
- **TITAN AI core:** a WebGL shader orb (react-three-fiber). It reacts to its states (idle, listening, thinking, acting, error) and to mic level. There's a CSS fallback if GPU acceleration in the VM is weak.
- **Dock:** minimal, with pinned and running apps. Running status comes from `windows`/`apps`.
- **Built-in apps:** Assistant (chat + plan view), Files, Terminal (xterm.js), System Monitor, Launcher (fuzzy search over .desktop entries), Security centre, Settings.
- **Internal multitasking:** a lightweight window manager inside the shell (draggable, resizable, z-order, snap). External Linux apps are managed through the `windows` service.
- **State:** Zustand stores fed by a single typed WebSocket client. RPC types are generated from backend Pydantic models into TypeScript so they never drift.

### 3.6 Repository layout
```
TITAN-OS/
  README.md  docs/ (architecture.md, protocol.md, security.md, dev-setup.md)
  backend/   pyproject.toml  titand/{core,services/*,tools,agent,db/migrations}  tests/
  shell/     Electron main + preload (TS), electron-builder config (linux arm64 AppImage/deb)
  ui/        React + TS + Vite app
  protocol/  shared schema → generated TS types
  scripts/   sync.sh, vm.sh, setup-vm.sh (reviewed before running), gen-types.sh
  .env.example  .gitignore (excludes .env, data, keys)
```

---

## 4. Technical limitations and risks
1. **Wayland:** Ubuntu 24.04 defaults to Wayland, where an app can't list, focus or move other apps' windows or inject input. **Mitigation:** use the "Ubuntu on Xorg" session. The dedicated TITAN X11 session later removes this dependency.
2. **GPU in UTM:** 3D acceleration is limited (virtio-gpu, or virgl if enabled). Heavy shaders may stutter. **Mitigation:** keep effects lightweight, cap frame rate, use the CSS fallback, and enable GPU-accelerated display in UTM if available.
3. **Microphone in UTM:** audio input passthrough needs UTM sound configured and macOS mic permission granted to UTM. **Mitigation:** we test this in Phase 0, before any voice work.
4. **whisper.cpp on VM CPU:** `base.en` runs roughly in real time, `small` is slower. Expect ~0.5–2 s latency per utterance. No GPU acceleration in the VM.
5. **Wake word** (always listening) costs CPU and is less reliable. We'll start with push-to-talk and a hotkey; a wake word is a later option (openWakeWord).
6. **Browser automation:** Playwright Chromium works on linux-arm64, but it controls its own browser instance, not your normal Firefox snap. That's a design constraint, not a bug.
7. **Not a real OS (yet):** it's a shell on top of Ubuntu. Kernel, boot and installer are out of scope until later phases (custom session, then optionally a branded ISO).
8. **Electron arm64 Linux** is supported. We avoid native Node modules so nothing needs compiling for the target.
9. **LLM reliability:** Claude can misread an instruction. The permission tiers, the plan preview and the trash-only policy keep mistakes recoverable.
10. **Cost and latency:** the Claude API is billed per use. Model routing and prompt caching reduce both. Nothing works offline except voice transcription and local tools.

---

## 5. Roadmap (each phase ends with real, tested functionality)

| Phase | Scope | Done when |
|---|---|---|
| **0. Foundations** | git init, repo skeleton, docs. VM setup script (reviewed by you, then run), SSH key, sync script. Verify Xorg session, mic passthrough, Electron runs in the VM | `scripts/vm.sh doctor` passes: SSH, Python 3.12, Node, Xorg, audio input level, Electron hello-world on the VM display |
| **1. Core plumbing** | titand skeleton, WS JSON-RPC, auth token, SQLite + migrations, Electron spawns backend, UI shell (charcoal desktop, dock, static core orb), generated types | `pytest` + `vitest` green; UI shows live backend connection status; restarting the backend reconnects automatically |
| **2. System services** | sysmon, fs (incl. trash), apps launcher, terminal (PTY + xterm.js), System Monitor, Files, Launcher, Terminal apps | Real CPU/mem graphs; browse, move and trash files in `$HOME`; launch Firefox from the launcher; interactive bash in the terminal |
| **3. AI assistant** | secrets (keyring), Claude streaming chat, tool registry, permissions engine + approval dialogs, audit log, Security centre | "List my largest files in Downloads" runs end-to-end; a destructive request shows an approval dialog and denying it blocks execution (tested) |
| **4. Windows and multitasking** | EWMH window service, dock running indicators, in-shell window manager, window tools for Claude | "Open Firefox and the terminal side by side" works in the Xorg VM |
| **5. Memory** | conversations persisted, memory extraction + FTS5 recall, preferences, memory viewer/editor | TITAN remembers a stated preference across app restarts; you can view and delete memories |
| **6. Voice** | push-to-talk capture, VAD, whisper.cpp, animated core reacting to the mic, optional local TTS (Piper) | Spoken command → transcript → executed action, with measured latency logged |
| **7. Automation and browser** | plan/checklist runner, pause/cancel, Playwright browser tools, automation history | Multi-step task ("download X, move it to Projects, open it") runs with per-step status and approvals |
| **8. Polish and packaging** | animations, theming, settings, error states, `.deb`/AppImage arm64 build, autostart | Clean install on a fresh Ubuntu ARM64 VM from the package |
| **9. TITAN session** | Own X11 login session (Openbox or a small Python window manager + Electron), GDM entry | Choosing "TITAN OS" at login boots straight into TITAN |

---

## 6. Engineering guardrails
- **No faked features.** Anything not implemented returns an explicit error and shows "not yet available" in the UI.
- **Testing:** pytest for every backend service, using temp dirs for fs and a stubbed Anthropic client only in unit tests. Integration tests run in the VM. Vitest + Testing Library for the UI. Every phase gate is written as a test or a reproducible script.
- **Mac safety:** nothing outside `/Users/bhuvanjabade/TITAN-OS` is touched. rsync pushes only to the VM; it never deletes on the Mac.
- **API keys:** stored in the VM keyring, never committed, never sent to the renderer, redacted from logs.
- **Approvals:** no system configuration changes (VM or Mac) without showing you the exact commands first.
- **Docs:** `docs/` is kept current with each phase. Each service gets a module docstring and its own section in architecture.md.

## 7. Verification (Phase 0 kickoff, after approval)
1. You enable SSH in the VM (I'll give you the exact commands), then I confirm `ssh titan-vm 'lsb_release -a; uname -m; echo $XDG_SESSION_TYPE'` shows 24.04, aarch64, x11.
2. Run `scripts/setup-vm.sh`, after you've reviewed it.
3. Run `scripts/vm.sh doctor`. All checks must pass before Phase 1 starts.
