#!/usr/bin/env bash
# Run on the Mac: copies the repo to the Ubuntu VM over SSH and (optionally)
# runs the installer there. Changes nothing on the Mac.
#   deploy/sync-to-vm.sh user@vm-host [--install]
set -euo pipefail
TARGET="${1:?usage: sync-to-vm.sh user@host [--install]}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"; DEST="${TITAN_VM_DIR:-TitanOS}"
rsync -az --delete --exclude .git --exclude node_modules --exclude .venv --exclude dist \
  --exclude __pycache__ --exclude '*.egg-info' --exclude .pytest_cache --exclude .env "$REPO/" "$TARGET:$DEST/"
echo "Synced to $TARGET:$DEST"
[ "${2:-}" = "--install" ] && ssh -t "$TARGET" "cd $DEST && deploy/install.sh"
