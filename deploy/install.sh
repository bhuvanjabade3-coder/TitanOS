#!/usr/bin/env bash
# TITAN OS installer for Ubuntu 24.04 (ARM64 or x86_64). Run on the TARGET
# machine (the Ubuntu VM), as your normal user. It installs only into your home
# directory and never uses sudo; missing system packages are listed for you.
#   deploy/install.sh [--autostart]   # --autostart opens the shell at login
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
AUTOSTART=0; [ "${1:-}" = "--autostart" ] && AUTOSTART=1
[ "$(uname -s)" = "Linux" ] || { echo "Run this on the Ubuntu target, not on macOS." >&2; exit 1; }
[ "$(id -u)" -ne 0 ] || [ -n "${TITAN_ALLOW_ROOT:-}" ] || { echo "Do not run as root (TITAN_ALLOW_ROOT=1 overrides, for containers/CI only)." >&2; exit 1; }

missing=()
need() { command -v "$1" >/dev/null || missing+=("$2"); }
need python3 python3; need npm npm; need node nodejs; need curl curl
python3 -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null || missing+=("python3 (>= 3.12)")
python3 -c 'import venv, ensurepip' 2>/dev/null || missing+=(python3-venv)
if [ ${#missing[@]} -gt 0 ]; then
  echo "Missing required packages. Install them, then re-run:"; echo "  sudo apt install ${missing[*]}"; exit 1
fi
optional=()
for pair in wmctrl:wmctrl xdotool:xdotool xdg-open:xdg-utils espeak-ng:espeak-ng arecord:alsa-utils pactl:pulseaudio-utils notify-send:libnotify-bin git:git; do
  command -v "${pair%%:*}" >/dev/null || optional+=("${pair##*:}")
done
python3 -c 'import gi; gi.require_version("Atspi", "2.0")' 2>/dev/null || optional+=(python3-gi gir1.2-atspi-2.0)

echo "==> Backend"
# --system-site-packages lets TITAN use the distro's AT-SPI (PyGObject) bindings.
[ -x "$REPO/backend/.venv/bin/python" ] || python3 -m venv --system-site-packages "$REPO/backend/.venv"
PY="$REPO/backend/.venv/bin/python"
"$PY" -m pip --version >/dev/null 2>&1 || "$PY" -m ensurepip --upgrade >/dev/null   # venvs made by other tools may lack pip
"$PY" -m pip install --quiet -e "$REPO/backend"

echo "==> Shell"
(cd "$REPO/frontend" && npm ci --no-audit --no-fund --silent && npm run build --silent)

echo "==> User configuration"
CONF="${XDG_CONFIG_HOME:-$HOME/.config}"; DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
mkdir -p "$CONF/titan" "$CONF/systemd/user" "$DATA/applications" "$HOME/.local/bin"
if [ ! -f "$CONF/titan/env" ]; then
  (umask 077; printf '# TITAN Core environment. Keep this file private (mode 600).\n# ANTHROPIC_API_KEY=\n' > "$CONF/titan/env")
fi
chmod 600 "$CONF/titan/env"
sed "s|@REPO@|$REPO|g" "$REPO/deploy/titan-core.service" > "$CONF/systemd/user/titan-core.service"
install -m 755 "$REPO/deploy/titan-shell" "$HOME/.local/bin/titan-shell"
cat > "$DATA/applications/titan.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=TITAN
Comment=AI-first desktop environment
Exec=$HOME/.local/bin/titan-shell
Icon=utilities-terminal
Categories=System;
DESK
if [ "$AUTOSTART" = 1 ]; then
  mkdir -p "$CONF/autostart"; cp "$DATA/applications/titan.desktop" "$CONF/autostart/titan.desktop"
fi

if systemctl --user show-environment >/dev/null 2>&1; then
  systemctl --user daemon-reload
  systemctl --user enable --now titan-core.service
  echo "==> titan-core service enabled and started"
else
  echo "==> No systemd user session here; start manually with:"
  echo "    TITAN_STATIC_DIR=$REPO/frontend/dist $REPO/backend/.venv/bin/titan-core"
fi
echo
echo "Installed. Next:"
echo "  1. Put your key in $CONF/titan/env (ANTHROPIC_API_KEY=...), then: systemctl --user restart titan-core"
echo "  2. Launch TITAN from the app grid, or run: titan-shell"
[ ${#optional[@]} -eq 0 ] || { echo "Optional features need:"; echo "  sudo apt install ${optional[*]}"; }
echo "  Voice input also needs whisper.cpp: deploy/setup-voice.sh"
