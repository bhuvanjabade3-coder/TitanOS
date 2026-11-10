#!/usr/bin/env bash
# Mac-side helpers for the UTM VM.
#   scripts/vm.sh ping            check SSH reachability + basic facts
#   scripts/vm.sh shell           open an interactive SSH session in the repo dir
#   scripts/vm.sh run <cmd...>    sync, then run a command in the repo dir on the VM
#   scripts/vm.sh doctor          sync, then run scripts/vm-doctor.sh on the VM (needs VM desktop logged in)
#   scripts/vm.sh tunnel [port]   forward VM's titand port (default 8765) to localhost
source "$(dirname "$0")/_common.sh"
cmd="${1:-help}"; shift || true
case "$cmd" in
  ping)
    vm_ssh 'echo "host: $(hostname)"; lsb_release -ds; echo "arch: $(uname -m)"; echo "python: $(python3 --version)"' ;;
  shell)
    ssh -t "${SSH_OPTS[@]}" "$VM_TARGET" "cd ~/$VM_DIR && exec \$SHELL -l" ;;
  run)
    "$SCRIPT_DIR/sync.sh" >/dev/null
    vm_ssh "cd ~/$VM_DIR && bash -lc $(printf '%q' "$*")" ;;
  doctor)
    "$SCRIPT_DIR/sync.sh" >/dev/null
    vm_ssh "cd ~/$VM_DIR && bash scripts/vm-doctor.sh" ;;
  tunnel)
    port="${1:-8765}"
    echo "forwarding localhost:$port → VM:$port (Ctrl-C to stop)"
    ssh -N "${SSH_OPTS[@]}" -L "$port:127.0.0.1:$port" "$VM_TARGET" ;;
  *)
    sed -n '2,7p' "$0" ;;
esac
