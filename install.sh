#!/bin/bash
# F1 Engineer one-line installer (macOS + Linux).
# Usage:  bash install.sh
set -e
cd "$(dirname "$0")"

echo "== system tools =="
if [ "$(uname)" = "Darwin" ]; then
  brew install ffmpeg espeak-ng portaudio 2>/dev/null || true
elif [ -f /etc/debian_version ]; then
  sudo apt-get update -qq && \
  sudo apt-get install -y ffmpeg espeak-ng portaudio19-dev 2>/dev/null || true
fi

echo "== python deps =="
python3 -m pip install --upgrade pip -q
python3 -m pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "== created .env — add your NVIDIA_API_KEY (free at build.nvidia.com) =="
fi

echo "Done. Run:  python3 app.py"
