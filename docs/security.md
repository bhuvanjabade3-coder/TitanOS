# Security model (summary — full design in architecture.md §3.3)

- **Only titand (the backend) can act on the system.** The UI talks to it over a localhost WebSocket protected by a random per-launch token.
- **Tool risk tiers:**
  - `read`: auto-allowed
  - `write`: ask once per scope
  - `destructive`: always ask
  - `forbidden`: never runs (sudo, paths outside `$HOME`, `~/.ssh`, `~/.gnupg`, secrets)
- **Deletes go to Trash only.**
- **Shell commands** are shown verbatim and run in a visible PTY.
- **Audit log:** every tool call, decision and result is recorded in SQLite.
- **API key:** stored in the VM's Secret Service keyring. It's never committed, never sent to the renderer, and redacted from logs. `.env`, `scripts/vm.env`, `*.db` and key files are gitignored.
- **Untrusted content:** file and web content returned by tools is marked untrusted in prompts and can never raise permissions.
