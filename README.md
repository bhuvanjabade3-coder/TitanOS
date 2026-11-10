# TITAN OS

An AI-first desktop environment for Ubuntu 24.04 ARM64. You control it with natural language and voice, powered by Claude.

**Status:** Phase 0 (foundations). No application code yet. See [docs/architecture.md](docs/architecture.md) for the architecture and roadmap.

| Path | Purpose |
|---|---|
| `backend/` | `titand`: Python 3.12 service (agent, tools, permissions, system services) |
| `shell/` | Electron desktop shell |
| `ui/` | React + TypeScript UI |
| `protocol/` | WebSocket JSON-RPC schema and generated types |
| `scripts/` | Mac↔VM dev loop, VM setup, environment doctor |
| `docs/` | Architecture, dev setup, security model |

Start here: [docs/dev-setup.md](docs/dev-setup.md).
