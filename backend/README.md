# TITAN Core (backend)

FastAPI service: configuration, logging, SQLite persistence, live system
telemetry, local API-token auth, and the shell-command risk classifier.

```bash
uv venv .venv && uv pip install -p .venv -e '.[dev]'
.venv/bin/pytest          # tests
.venv/bin/titan-core      # serves on 127.0.0.1:8710
```

Configuration is by environment variable (`TITAN_HOST`, `TITAN_PORT`,
`TITAN_DATA_DIR`, `TITAN_LOG_LEVEL`, `TITAN_REQUIRE_TOKEN`) or `.env`.
`ANTHROPIC_API_KEY` is read from the environment only and is never logged or
returned by the API. Data lives in `$XDG_DATA_HOME/titan` (database, logs,
`api_token` with mode 0600).

Every `/api/*` and `/ws/*` request needs `Authorization: Bearer <api_token>`;
`/health` is public. `/api/terminal/classify` classifies a command and never
executes it.
