# F1 Engineer — push-to-talk pit-wall voice agent (Mac, Linux, Windows)

Talk to your race engineer while you game. Hold a key, speak, release —
he answers out loud in a floating F1 team-radio card. Swear at him and
he swears back. Be nice and he's a mate.

- 🖥️ **See-through ENGINEER overlay** — live timer, freq bars, latest
  exchange only. Drag to move, right-click to quit.
- 🎙️ **Global hold-to-talk** (Right Option) — works while you're in-game.
- 🧠 **NVIDIA brain** (free Build API, OpenAI-compatible) + local tools:
  volume, media, apps, brightness, system info, file writing.
- 👂 **Local speech-to-text** — Whisper `tiny.en` on your machine, offline
  after first download. Optional upgrade: NVIDIA Parakeet v2.
- 🔊 **Local voice** — Kokoro-82M, offline. Free Edge-TTS + Mac `say`
  fallbacks built in.
- 😡 **Mood mirror** — calm driver gets a mate, feral driver gets both
  barrels.
- 🏁 **Live F1 timing** — positions, laps, weather, sessions via the free
  OpenF1 API (historical, no key).
- 🌐 **Internet** — free DuckDuckGo search + page reader, no key.
- 📁 **Computer access** — files sandboxed to `~/Documents/f1-jarvis-files`
  (list/read/write), cross-platform app/volume/media/brightness controls.

## Install

```zsh
bash install.sh        # macOS / Linux  (or install.bat on Windows)
# then add NVIDIA_API_KEY to .env
```

Manual: `brew install ffmpeg espeak-ng` (or apt/winget equivalents),
`pip install -r requirements.txt`, `cp .env.example .env`.

## API keys (1 needed)

| Key | Where | Cost | Used for |
|---|---|---|---|
| `NVIDIA_API_KEY` | [build.nvidia.com](https://build.nvidia.com) → profile → API keys | free tier | the brain (answers) |

Put it in `.env`. Everything else (Whisper, Kokoro, OpenF1 timing)
runs free with no keys. `.env` is git-ignored — never commit it.

Optional upgrades (all auto-detected, no code changes):
- **Parakeet v2 STT**: `pip install "nemo_toolkit[asr]" torch`
- **Edge-TTS voice**: set `TTS_VOICE` (e.g. `en-AU-NatashaNeural`)
- **Kokoro voice/speed**: `KOKORO_VOICE=bm_lewis`, `KOKORO_MODEL=model_q8f16.onnx`

## Run

```zsh
python3 app.py
```

Look at the **right edge** of your screen for the black + gold card.

## Controls

| Action | How |
|---|---|
| Talk (works in-game) | **hold RIGHT OPTION**, speak, release |
| Talk (backup) | hold the card footer |
| Move card | drag it |
| Quit | right-click the card |
| Change hotkey | `HOTKEY_HOLD` at top of `app.py` (`alt_r`, `f9`, `caps_lock`, `ctrl_r`) |

## macOS permissions (one time)

- **Input Monitoring** → Terminal ON (else the hotkey can't hear you
  in-game): Settings → Privacy & Security → Input Monitoring.
- **Microphone** → allow Terminal on first talk.

Play games in **borderless/windowed** mode — true fullscreen hides all
overlays on macOS.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Hotkey does nothing | Input Monitoring (above) |
| `PortAudioError -9986` | fixed in-app (mic picker + retry); still stuck → unplug/replug headset, rerun |
| First talk hangs minutes | first-time model download (~100MB Whisper, ~160MB Kokoro), then offline |
| Brain slow once in a while | free-tier queue; terminal shows `brain took Xs` per reply |
| No window appears | run `python3 app.py --test` — card flashes 2.5s if rendering works |

## Files

| File | What |
|---|---|
| `app.py` | the app: overlay + hotkey + mic + pipeline |
| `brain.py` | Aussie personality, mood mirror, tools, NVIDIA calls |
| `tts.py` | voice router (kokoro → edge → say) |
| `tools_mac.py` / `tools_f1.py` | Mac controls / OpenF1 timing |
| `main.py` | terminal-only version (no overlay) |
| `server.py` + `radio_wall.html` | browser radio wall (legacy extra) |

Inspired by [quick-assistant](https://github.com/sloganking/quick-assistant).
Timing by [OpenF1](https://openf1.org). Not affiliated with Formula 1.
