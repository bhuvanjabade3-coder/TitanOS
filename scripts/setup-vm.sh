#!/usr/bin/env bash
# TITAN OS — one-time Ubuntu 24.04 ARM64 VM setup. RUN INSIDE THE VM, NOT ON THE MAC.
# Prints every action and asks for confirmation before changing anything.
# It does NOT: change the default session, modify AppArmor, touch sshd config, or use --no-sandbox.
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then echo "refusing: this script is for the Ubuntu VM only" >&2; exit 1; fi
if [[ $EUID -eq 0 ]]; then echo "run as your normal user (sudo is invoked only for apt)" >&2; exit 1; fi

APT_PKGS=(
  build-essential cmake pkg-config git curl rsync   # toolchain (whisper.cpp builds with cmake)
  python3-venv python3-dev python3-pip              # titand runtime (Python 3.12)
  wmctrl xdotool x11-utils                          # EWMH window control (X11 session)
  alsa-utils pulseaudio-utils portaudio19-dev       # mic capture + diagnostics
  libsecret-1-0 libsecret-tools gnome-keyring       # API-key storage via Secret Service
  libnss3 libgbm1 libasound2t64 libgtk-3-0t64       # Electron runtime libs
)
NVM_VERSION=v0.40.3
NODE_MAJOR=24

echo "== TITAN OS VM setup =="
echo "1) sudo apt-get update && sudo apt-get install -y ${APT_PKGS[*]}"
echo "2) install nvm $NVM_VERSION into ~/.nvm (user-level) and Node $NODE_MAJOR LTS"
echo
read -r -p "Proceed? [y/N] " ans
[[ "$ans" == "y" || "$ans" == "Y" ]] || { echo "aborted, nothing changed"; exit 0; }

sudo apt-get update
sudo apt-get install -y "${APT_PKGS[@]}"

if [[ ! -s "$HOME/.nvm/nvm.sh" ]]; then
  curl -fsSL "https://raw.githubusercontent.com/nvm-sh/nvm/$NVM_VERSION/install.sh" -o /tmp/nvm-install.sh
  echo "downloaded nvm installer to /tmp/nvm-install.sh (inspect it if you like)"
  read -r -p "Run nvm installer? [y/N] " ans
  [[ "$ans" == "y" || "$ans" == "Y" ]] && bash /tmp/nvm-install.sh
fi
# shellcheck disable=SC1091
source "$HOME/.nvm/nvm.sh"
nvm install "$NODE_MAJOR"
nvm alias default "$NODE_MAJOR"

echo
echo "Done. Manual steps remaining:"
echo "  - Log out, click the gear icon on the login screen, choose 'Ubuntu on Xorg', log in."
echo "  - Then from the Mac: scripts/vm.sh doctor"
