# Development setup (macOS host → Ubuntu ARM64 VM in UTM)

## 1. Enable SSH in the VM (once, in the Ubuntu terminal)
```bash
sudo apt-get update && sudo apt-get install -y openssh-server
sudo systemctl enable --now ssh
ip -4 addr show | grep inet        # note the 192.168.64.x address
```

## 2. Key-based SSH from the Mac (once)
```bash
ssh-keygen -t ed25519 -f ~/.ssh/titan_vm_ed25519 -C titan-vm
ssh-copy-id -i ~/.ssh/titan_vm_ed25519.pub <vm-user>@<vm-ip>
cp scripts/vm.env.example scripts/vm.env   # fill in VM_HOST, VM_USER, SSH_KEY
scripts/vm.sh ping
```

## 3. Provision the VM
```bash
scripts/sync.sh
scripts/vm.sh shell
# now inside the VM, in ~/titan-os:
bash scripts/setup-vm.sh                  # shows every action and asks before each step
```
Then log out of the VM desktop, choose **Ubuntu on Xorg** (gear icon on the login screen) and log back in.

## 4. Verify
```bash
scripts/vm.sh doctor     # from the Mac; the VM desktop must be logged in
```
Speak during the 2-second microphone test. Phase 1 starts once there are 0 failures.

## Daily loop
| Command | What it does |
|---|---|
| `scripts/sync.sh` | One-way push Mac → VM (never deletes on the Mac) |
| `scripts/vm.sh run <cmd>` | Sync, then run a command in the repo on the VM |
| `scripts/vm.sh tunnel` | Forward the VM's titand port 8765 to the Mac (for Vite on the Mac) |

## Known VM caveats
- **Wayland:** window control doesn't work under Wayland. Use the Xorg session.
- **Electron sandbox:** Ubuntu 24.04's AppArmor userns restriction breaks Electron's sandbox. The fix is an AppArmor profile, which will be proposed for your approval. We never ship `--no-sandbox`.
- **Microphone:** in UTM, VM settings → Sound must be enabled, and macOS must grant UTM microphone permission (System Settings → Privacy & Security → Microphone).
