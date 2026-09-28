@echo off
REM F1 Engineer one-line installer (Windows).
REM Usage:  install.bat
REM Requires: Python 3.10+ and ffmpeg on PATH
REM   winget install Gyan.FFmpeg
REM   winget install eSpeak-ng.eSpeak-ng
cd /d "%~dp0"

python -m pip install --upgrade pip -q
python -m pip install -r requirements.txt

if not exist .env (
  copy .env.example .env
  echo Created .env - add your NVIDIA_API_KEY (free at build.nvidia.com)
)

echo Done. Run:  python app.py
