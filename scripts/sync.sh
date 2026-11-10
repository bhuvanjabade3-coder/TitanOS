#!/usr/bin/env bash
# Push the repo from the Mac to the VM. One-way: never deletes anything on the Mac.
# --delete only prunes files inside the VM's copy of the repo that no longer exist here.
source "$(dirname "$0")/_common.sh"
cd "$REPO_ROOT"
vm_ssh "mkdir -p ~/$VM_DIR"
rsync -az --delete \
  --exclude '.git/' --exclude 'node_modules/' --exclude '.venv/' \
  --exclude 'data/' --exclude 'dist/' --exclude 'out/' --exclude 'release/' \
  --exclude '__pycache__/' --exclude '.DS_Store' \
  --exclude '.env' --exclude 'scripts/vm.env' \
  -e "ssh ${SSH_OPTS[*]}" \
  ./ "$VM_TARGET:$VM_DIR/"
echo "synced → $VM_TARGET:~/$VM_DIR"
