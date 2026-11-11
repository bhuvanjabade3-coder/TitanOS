#!/usr/bin/env bash
# Removes TITAN's user-level integration. Your data (memory, settings, logs) is
# kept unless you pass --purge, which asks before deleting it.
set -euo pipefail
CONF="${XDG_CONFIG_HOME:-$HOME/.config}"; DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
systemctl --user disable --now titan-core.service 2>/dev/null || true
rm -f "$CONF/systemd/user/titan-core.service" "$CONF/autostart/titan.desktop" "$DATA/applications/titan.desktop" "$HOME/.local/bin/titan-shell"
systemctl --user daemon-reload 2>/dev/null || true
echo "TITAN integration removed."
if [ "${1:-}" = "--purge" ]; then
  read -r -p "Permanently delete all TITAN data in $DATA/titan and $CONF/titan? [y/N] " a
  [ "$a" = "y" ] && rm -rf "$DATA/titan" "$CONF/titan" && echo "Data deleted." || echo "Data kept."
else
  echo "Data kept in $DATA/titan (use --purge to delete it)."
fi
