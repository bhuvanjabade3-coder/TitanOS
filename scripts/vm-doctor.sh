#!/usr/bin/env bash
# TITAN OS — environment checks. Runs INSIDE the VM (invoked over SSH by scripts/vm.sh doctor).
# Read-only except: installs electron into scripts/electron-smoke/node_modules and writes a temp WAV.
set -uo pipefail
cd "$(dirname "$0")/.."
PASS=0; FAIL=0; WARN=0
ok()   { echo "  [PASS] $*"; PASS=$((PASS+1)); }
bad()  { echo "  [FAIL] $*"; FAIL=$((FAIL+1)); }
warn() { echo "  [WARN] $*"; WARN=$((WARN+1)); }

UID_N=$(id -u)
export XDG_RUNTIME_DIR="/run/user/$UID_N"

echo "== System"
. /etc/os-release
[[ "$VERSION_ID" == "24.04" ]] && ok "Ubuntu $VERSION_ID" || warn "Ubuntu $VERSION_ID (expected 24.04)"
[[ "$(uname -m)" == "aarch64" ]] && ok "arch aarch64" || bad "arch $(uname -m)"

echo "== Toolchain"
python3 -c 'import sys; assert sys.version_info[:2]>=(3,12)' 2>/dev/null && ok "$(python3 --version)" || bad "python3 >= 3.12 missing"
python3 -m venv --help >/dev/null 2>&1 && ok "python3-venv" || bad "python3-venv missing"
[[ -s "$HOME/.nvm/nvm.sh" ]] && source "$HOME/.nvm/nvm.sh" >/dev/null 2>&1
if command -v node >/dev/null; then
  major=$(node -p 'process.versions.node.split(".")[0]')
  (( major >= 22 )) && ok "node $(node --version)" || bad "node $(node --version) (need >= 22)"
else bad "node not found (run scripts/setup-vm.sh)"; fi
for t in cmake gcc git wmctrl xdotool arecord secret-tool; do
  command -v "$t" >/dev/null && ok "$t" || bad "$t missing"
done

echo "== Graphical session"
SESSION_TYPE=""
for s in $(loginctl list-sessions --no-legend 2>/dev/null | awk -v u="$USER" '$3==u{print $1}'); do
  t=$(loginctl show-session "$s" -p Type --value 2>/dev/null)
  [[ "$t" == "x11" || "$t" == "wayland" ]] && SESSION_TYPE="$t"
done
case "$SESSION_TYPE" in
  x11) ok "desktop session is X11" ;;
  wayland) bad "desktop session is Wayland — log out, choose 'Ubuntu on Xorg'" ;;
  *) bad "no graphical session for $USER — log into the VM desktop first" ;;
esac
export DISPLAY="${DISPLAY:-:0}"
for xa in "$XDG_RUNTIME_DIR/gdm/Xauthority" "$HOME/.Xauthority"; do [[ -f "$xa" ]] && export XAUTHORITY="$xa" && break; done
if [[ "$SESSION_TYPE" == "x11" ]]; then
  wm=$(wmctrl -m 2>/dev/null | awk -F': ' '/^Name/{print $2}')
  [[ -n "$wm" ]] && ok "EWMH window manager reachable ($wm)" || bad "wmctrl cannot reach display $DISPLAY"
  n=$(wmctrl -l 2>/dev/null | wc -l); ok "wmctrl sees $n window(s)"
fi

echo "== Electron sandbox prerequisites"
r=$(sysctl -n kernel.apparmor_restrict_unprivileged_userns 2>/dev/null || echo "?")
if [[ "$r" == "1" ]]; then
  warn "AppArmor restricts unprivileged userns (Ubuntu 24.04 default). Electron's sandbox needs an AppArmor profile — will be proposed for approval in Phase 1. We will NOT use --no-sandbox."
else ok "unprivileged userns allowed ($r)"; fi

echo "== Microphone"
WAV=$(mktemp --suffix=.wav)
if timeout 6 arecord -q -d 2 -f S16_LE -r 16000 -c 1 "$WAV" 2>/dev/null; then
  peak=$(python3 - "$WAV" <<'PY'
import sys, wave, array
w = wave.open(sys.argv[1]); a = array.array("h", w.readframes(w.getnframes()))
print(max((abs(x) for x in a), default=0))
PY
)
  if (( peak > 300 )); then ok "mic captured audio (peak $peak/32767)"
  else warn "mic recorded but near-silent (peak $peak). Speak during the test, check UTM sound + macOS mic permission for UTM"; fi
else bad "arecord failed — check UTM audio device and PipeWire"; fi
rm -f "$WAV"

echo "== Electron smoke test"
if [[ "$SESSION_TYPE" == "x11" ]] && command -v npm >/dev/null; then
  ( cd scripts/electron-smoke && [[ -d node_modules/electron ]] || npm install --silent --no-audit --no-fund >/dev/null 2>&1 )
  out=$(cd scripts/electron-smoke && timeout 30 npx --no-install electron . 2>&1)
  if grep -q TITAN_SMOKE_OK <<<"$out"; then ok "Electron opened a window on $DISPLAY ($(grep -o 'electron [0-9.]*' <<<"$out"))"
  else bad "Electron failed:"; echo "$out" | tail -5 | sed 's/^/        /'; fi
else warn "skipped (needs X11 session + node)"; fi

echo
echo "Result: $PASS passed, $WARN warnings, $FAIL failed"
(( FAIL == 0 ))
