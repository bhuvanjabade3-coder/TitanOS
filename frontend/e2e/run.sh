#!/usr/bin/env bash
# Runs the shell end-to-end test against a throwaway TITAN Core. Nothing here
# touches your real home directory or TITAN data.
set -euo pipefail
cd "$(dirname "$0")/.."
W="$(mktemp -d "${TMPDIR:-/tmp}/titan-e2e.XXXXXX")"
CORE_PORT="${TITAN_E2E_CORE_PORT:-8799}"; WEB_PORT="${TITAN_E2E_WEB_PORT:-5199}"
mkdir -p "$W/home/Documents" "$W/data" "$W/share/applications" "${TITAN_E2E_SHOTS:-$W/shots}"
echo "hello from titan" > "$W/home/Documents/notes.txt"
printf '[Desktop Entry]\nType=Application\nName=Firefox Web Browser\nExec=touch %s/launched\nCategories=Network;WebBrowser;\n' "$W" \
  > "$W/share/applications/firefox.desktop"
cleanup() { kill "${CORE_PID:-}" "${WEB_PID:-}" 2>/dev/null || true; [ -n "${TITAN_E2E_KEEP:-}" ] || rm -rf "$W"; }
trap cleanup EXIT
env -u ANTHROPIC_API_KEY TITAN_DATA_DIR="$W/data" TITAN_HOME="$W/home" TITAN_PORT="$CORE_PORT" \
  XDG_DATA_DIRS="$W/share" XDG_DATA_HOME="$W/none" ../backend/.venv/bin/titan-core > "$W/core.log" 2>&1 & CORE_PID=$!
TITAN_DATA_DIR="$W/data" TITAN_CORE_URL="http://127.0.0.1:$CORE_PORT" node node_modules/vite/bin/vite.js --port "$WEB_PORT" --strictPort > "$W/vite.log" 2>&1 & WEB_PID=$!
for _ in $(seq 60); do curl -sf "http://127.0.0.1:$WEB_PORT/health" > /dev/null 2>&1 && break; sleep 0.5; done
TITAN_E2E_URL="http://127.0.0.1:$WEB_PORT" TITAN_E2E_HOME="$W/home" node "${TITAN_E2E_SCRIPT:-e2e/shell.e2e.cjs}"
