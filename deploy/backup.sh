#!/usr/bin/env bash
# Consistent backup of TITAN's database, preferences and plugins.
#   deploy/backup.sh [output-dir]      restore with deploy/restore.sh <archive>
set -euo pipefail
DATA="${TITAN_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/titan}"
OUT="${1:-$HOME/titan-backups}"; STAMP="$(date +%Y%m%d-%H%M%S)"
[ -f "$DATA/titan.db" ] || { echo "No TITAN database at $DATA" >&2; exit 1; }
mkdir -p "$OUT"; TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
# sqlite's online backup API gives a consistent copy even while core is running
python3 - "$DATA/titan.db" "$TMP/titan.db" <<'PY'
import sqlite3, sys
src, dst = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
with dst: src.backup(dst)
PY
[ -d "$DATA/plugins" ] && cp -r "$DATA/plugins" "$TMP/plugins"
(umask 077; tar -C "$TMP" -czf "$OUT/titan-$STAMP.tar.gz" .)
echo "$OUT/titan-$STAMP.tar.gz"
