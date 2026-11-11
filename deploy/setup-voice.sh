#!/usr/bin/env bash
# Builds whisper.cpp and downloads a speech model into TITAN's data directory
# (user-level, no sudo). Needs: git cmake build-essential, and network access.
#   deploy/setup-voice.sh [model]     model defaults to base.en
set -euo pipefail
MODEL="${1:-base.en}"
DATA="${TITAN_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/titan}"
for t in git cmake make c++; do command -v "$t" >/dev/null || { echo "Missing $t. Install with: sudo apt install git cmake build-essential" >&2; exit 1; }; done
mkdir -p "$DATA/models"
[ -d "$DATA/whisper.cpp" ] || git clone --depth 1 https://github.com/ggml-org/whisper.cpp "$DATA/whisper.cpp"
cmake -S "$DATA/whisper.cpp" -B "$DATA/whisper.cpp/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$DATA/whisper.cpp/build" -j --config Release
bash "$DATA/whisper.cpp/models/download-ggml-model.sh" "$MODEL" "$DATA/models"
echo "Done. Check Settings → Voice in TITAN. For speech output: sudo apt install espeak-ng alsa-utils"
