#!/usr/bin/env bash
# Shared config loader for Mac-side scripts. Reads scripts/vm.env (gitignored).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$SCRIPT_DIR/vm.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: $ENV_FILE not found. Copy scripts/vm.env.example to scripts/vm.env and fill it in." >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"
: "${VM_HOST:?VM_HOST not set in vm.env}" "${VM_USER:?VM_USER not set in vm.env}"
VM_DIR="${VM_DIR:-titan-os}"
SSH_OPTS=(-o ConnectTimeout=5)
[[ -n "${SSH_KEY:-}" ]] && SSH_OPTS+=(-i "${SSH_KEY/#\~/$HOME}")
VM_TARGET="$VM_USER@$VM_HOST"
vm_ssh() { ssh "${SSH_OPTS[@]}" "$VM_TARGET" "$@"; }
