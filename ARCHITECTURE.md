# Architecture

```
 TITAN Shell (React)  ──HTTP/WS──►  TITAN Core (FastAPI, 127.0.0.1:8710)
   windows, dock, apps                 │
                                       ├─ Registry ── gate ── policy ── approvals ── audit
 Voice ───────────────────────────────►│      ▲
 Claude tool loop (titan/ai.py) ───────┘      │ every caller goes through here
 Plugins (PluginAPI) ─────────────────────────┘
                                       ├─ actions/  files terminal apps desktop browser
                                       │            memory security settings dev misc
                                       ├─ TaskManager (threads, path locks, cancel)
                                       ├─ Notifier + reminders      EventBus → /ws/events
                                       └─ SQLite (WAL, migrations)
```

## Core idea: one action registry

Everything TITAN can do is an *action* (`fs.move`, `terminal.run`, `apps.launch`…)
registered in `titan/core.py`. The UI, the assistant, voice and plugins all call
`Registry.perform(actor, name, params)`. There is no second code path to the
system, so the safety rules are written once:

1. Parameters are validated against the action's schema.
2. The action's **gate** classifies this specific request as low / medium / high
   risk (e.g. `fs.delete` is always high; `terminal.run` uses the command
   classifier; `fs.move` becomes medium when it is a bulk operation).
3. **Policy** decides: run, ask, or deny (see SECURITY.md).
4. If it must ask, an **approval** is stored with the exact parameters. Approving
   executes those parameters; the approval is single-use and expires in 15 minutes.
5. Every attempt and outcome is written to the **audit log**.

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Python + FastAPI core, React shell | As specified; Python has first-class access to psutil, D-Bus/AT-SPI bindings and subprocess control on Linux. |
| 2 | Single registry for all capabilities | Guarantees the assistant, voice and plugins cannot bypass permission checks that the UI obeys. |
| 3 | Hand-written Claude tool loop, not the SDK tool runner | TITAN must own the step between model turns: a tool call can come back "awaiting approval", must be audited, and must emit progress events. The loop is ~60 lines and has no beta dependency for its control flow. |
| 4 | Approvals execute stored parameters server-side | An approval can never be replayed for a different command, and the result is reported to whoever asked. |
| 5 | The model is told the true outcome of every tool call, including "NOT EXECUTED, awaiting approval" | Prevents the assistant from claiming work that did not happen. |
| 6 | Conversation history is replayed as text only across turns | Robust across model changes and restarts; within a turn the full tool/thinking blocks are passed back unchanged. Trade-off: the model does not re-see earlier raw tool output. |
| 7 | Local API token on every request, even on loopback | Any web page in a browser can reach 127.0.0.1. The token (0600 file) proves the caller is a TITAN client. |
| 8 | Token reaches the shell via the URL fragment | Fragments are never sent over HTTP, so other local users cannot fetch it from the port. In development the Vite proxy attaches it server-side instead. |
| 9 | Browser app-mode window instead of Electron (for now) | Same UI, no ~200 MB runtime to build for ARM64, nothing to keep patched. An Electron wrapper remains possible; nothing in the shell depends on the choice. |
| 10 | Integrate with GNOME rather than replace the window manager | As specified. System windows are managed through EWMH (`wmctrl`) and `xdotool`; TITAN's own apps use an in-shell window manager. Requires Xorg, not Wayland. |
| 11 | File operations confined to the home directory, credential stores excluded | Limits the blast radius of any mistaken or malicious request; symlinks are resolved before the check. |
| 12 | Writes to login/startup paths are always high risk | `~/.bashrc`, autostart, systemd user units and `.desktop` files are persistence mechanisms; "allow" preferences never cover them. |
| 13 | Terminal allowlist, not blocklist | A command is low risk only if every segment is a known read-only program. Unknown means "ask". |
| 14 | Trash by default (freedesktop spec), permanent delete always asks | Recoverable by default; compatible with GNOME Files. |
| 15 | Tasks run in threads with path locks; conflicting tasks are refused | Simple, sufficient for I/O-bound work, and prevents two tasks modifying the same files. Tasks do not survive a restart and are marked `interrupted`. |
| 16 | SQLite with append-only migrations, WAL mode | As specified; each migration is atomic and tested for rollback. |
| 17 | Plugins are in-process Python behind a capability API | Simple to write. It is capability mediation, not a sandbox (see SECURITY.md); out-of-process plugins are on the roadmap. |
| 18 | Voice shells out to whisper.cpp, espeak-ng/piper and arecord | Fully local, no Python audio dependencies to build on ARM64. Wake word is detected by transcribing short chunks, which is simple but less efficient than a dedicated detector. |
| 19 | Optional host tools are discovered at call time and reported when missing | A missing `wmctrl` yields "install wmctrl", never a silent no-op. |
| 20 | Minimised and off-workspace shell windows stay mounted | Their state (terminal output, drafts) must survive. |
| 21 | No exit animations on modals or windows | An animation that fails to finish must never leave a dead overlay over an approval prompt. |
| 22 | Default model `claude-opus-5-5`, adaptive thinking, server-side refusal fallbacks | Configurable with `TITAN_AI_MODEL` / `TITAN_AI_EFFORT`. |

## Data

`$XDG_DATA_HOME/titan/`: `titan.db`, `api_token` (0600), `logs/`, `plugins/`,
`models/` (whisper), `whisper.cpp/`. Secrets live only in `~/.config/titan/env`.

## Configuration

Environment variables, prefix `TITAN_`: `HOST`, `PORT`, `DATA_DIR`, `HOME`,
`LOG_LEVEL`, `REQUIRE_TOKEN`, `AI_MODEL`, `AI_EFFORT`, `AI_MAX_STEPS`,
`WHISPER_BIN`, `WHISPER_MODEL`, `STATIC_DIR`. Plus `ANTHROPIC_API_KEY`.
User preferences (theme, dock, permissions, voice…) are stored in SQLite.
