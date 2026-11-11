#!/usr/bin/env bash
# Restores a backup made by backup.sh. The current database is kept alongside
# as titan.db.before-restore, so a restore can itself be undone.
set -euo pipefail
ARCHIVE="${1:?usage: restore.sh <titan-backup.tar.gz>}"
DATA="${TITAN_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/titan}"
tar -tzf "$ARCHIVE" | grep -qx './titan.db' || { echo "Not a TITAN backup: $ARCHIVE" >&2; exit 1; }
systemctl --user stop titan-core.service 2>/dev/null || true
mkdir -p "$DATA"
[ -f "$DATA/titan.db" ] && cp "$DATA/titan.db" "$DATA/titan.db.before-restore"
rm -f "$DATA/titan.db-wal" "$DATA/titan.db-shm"
tar -C "$DATA" -xzf "$ARCHIVE"
systemctl --user start titan-core.service 2>/dev/null || echo "Start TITAN Core to use the restored data."
echo "Restored into $DATA"
