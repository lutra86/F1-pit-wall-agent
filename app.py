"""F1 Pit-Wall Jarvis — native Mac app.

- Lives on the side of the screen as a see-through always-on-top overlay.
- Global hold-to-talk hotkey works while you're in other apps / games.
- Speech-to-text built in (local Parakeet v2 if installed, else whisper).
- Brain: local tools + NVIDIA API. Voice replies spoken aloud (Edge-TTS).

Run:  python3 app.py
Talk: HOLD Right-Option, speak, release. (Change HOTKEY below if it
      clashes with your game. Backup: hold the TALK button in the overlay.)
Quit: press the X button in the overlay.
"""
import asyncio
import os
import queue
import re
import subprocess
import threading
import tkinter as tk
from pathlib import Path

# ---------------- config ----------------
HOTKEY_HOLD = "alt_r"          # hold-to-talk key: alt_r (Right Option).
                               # Other options: "f9", "caps_lock", "ctrl_r".
HOTKEY_LABEL = {"alt_r": "RIGHT OPTION", "alt_l": "LEFT OPTION",
                "ctrl_r": "RIGHT CTRL", "ctrl_l": "LEFT CTRL",
                "f9": "F9", "caps_lock": "CAPS LOCK"}.get(HOTKEY_HOLD,
                                                          HOTKEY_HOLD.upper())
# Speech-to-text backend: "auto" tries Parakeet v2 (NeMo) first, then whisper.
# For others installing fresh: pip install "nemo_toolkit[asr]" torch
#   (downloads nvidia/parakeet-tdt-0.6b-v2 once, ~2.4GB, then fully offline).
STT_BACKEND = os.getenv("STT_BACKEND", "auto")  # auto | parakeet | whisper
PARAKEET_MODEL = os.getenv("PARAKEET_MODEL", "nvidia/parakeet-tdt-0.6b-v2")
WHISPER_MODEL = "tiny.en"      # fallback local STT (downloaded once, ~75MB).
TTS_VOICE = os.getenv("TTS_VOICE", "en-AU-WilliamMultilingualNeural")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.2-11b-vision-instruct")
SAMPLE_RATE = 16000
# ----------------------------------------

BASE_DIR = Path(__file__).parent
BEEP = BASE_DIR / "assets" / "beep.mp3"
REPLY_MP3 = BASE_DIR / "assets" / "reply.mp3"

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import tools_mac as mac
import tools_f1 as f1

events: "queue.Queue[tuple]" = queue.Queue()  # (kind, text)
recording = {"active": False, "frames": []}
_stt = {"backend": None, "model": None}


def stt_backend() -> str:
    """Pick STT backend: Parakeet v2 if NeMo is installed, else whisper."""
    if _stt["backend"]:
        return _stt["backend"]
    if STT_BACKEND in ("auto", "parakeet"):
        try:
            import nemo.collections.asr  # noqa: F401
            _stt["backend"] = "parakeet"
            return "parakeet"
        except ImportError:
            if STT_BACKEND == "parakeet":
                raise RuntimeError(
                    "STT_BACKEND=parakeet but nemo is not installed. "
                    'Run: pip install "nemo_toolkit[asr]"')
    _stt["backend"] = "whisper"
    return "whisper"


# ---------- speech-to-text (local models, no cloud) ----------
def whisper():
    if _stt["model"] is None or _stt.get("which") != "whisper":
        events.put(("status", "LOADING whisper tiny.en (~75MB first time)…"))
        from faster_whisper import WhisperModel
        _stt["model"] = WhisperModel(WHISPER_MODEL, device="cpu",
                                     compute_type="int8")
        _stt["which"] = "whisper"
        events.put(("status", f"READY — hold {HOTKEY_LABEL} to talk"))
    return _stt["model"]


def parakeet():
    if _stt["model"] is None or _stt.get("which") != "parakeet":
        events.put(("status", f"LOADING {PARAKEET_MODEL} (once, ~2.4GB)…"))
        import nemo.collections.asr as nemo_asr
        _stt["model"] = nemo_asr.models.ASRModel.from_pretrained(
            model_name=PARAKEET_MODEL)
        _stt["model"].eval()
        _stt["which"] = "parakeet"
        events.put(("status", f"READY — hold {HOTKEY_LABEL} to talk"))
    return _stt["model"]


def transcribe(wav_path: str) -> str:
    if stt_backend() == "parakeet":
        out = parakeet().transcribe([wav_path])
        text = out[0].text if hasattr(out[0], "text") else str(out[0])
        return text.strip()
    model = whisper()
    segments, _ = model.transcribe(wav_path, beam_size=1)
    return "".join(s.text for s in segments).strip()


# ---------- brain (shared, Aussie + mood mirror) ----------
from brain import think  # noqa: E402  (needs sys.path = script dir)


# ---------- speech-out ----------
def play(path: Path):
    subprocess.run(["afplay", str(path)], capture_output=True)


_BEEP_DATA, _BEEP_RATE = None, None

def preload_beep():
    """Decode the F1 beep once at startup so it fires instantly on keypress
    (spawning afplay each time costs ~half a second)."""
    global _BEEP_DATA, _BEEP_RATE
    try:
        import numpy as np
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(BEEP),
             "-ar", "44100", "-ac", "1", "-f", "f32le", "-"],
            capture_output=True, check=True).stdout
        _BEEP_DATA = np.frombuffer(raw, dtype=np.float32)
        _BEEP_RATE = 44100
        print("[jarvis] beep preloaded, fires instantly.", flush=True)
    except Exception as e:
        print(f"[jarvis] beep preload failed ({e}), using afplay fallback.",
              flush=True)


def beep_now():
    """Fire the beep immediately (non-blocking)."""
    try:
        if _BEEP_DATA is not None:
            import sounddevice as sd
            sd.play(_BEEP_DATA, _BEEP_RATE)
            return
    except Exception:
        pass
    threading.Thread(target=play, args=(BEEP,), daemon=True).start()


async def _speak(text: str):
    import edge_tts
    await edge_tts.Communicate(text, TTS_VOICE).save(str(REPLY_MP3))
    play(REPLY_MP3)


def speak(text: str):
    events.put(("status", "SPEAKING…"))
    try:
        print("[jarvis] speaking via edge-tts…", flush=True)
        asyncio.run(_speak(text))
        print("[jarvis] done speaking.", flush=True)
    except Exception as e:
        print(f"[jarvis] edge-tts failed ({e}), using offline Mac voice…",
              flush=True)
        events.put(("status", "online voice failed — offline voice…"))
        subprocess.run(["say", text], capture_output=True)
    events.put(("status", f"READY — hold {HOTKEY_LABEL} to talk"))


# ---------- talk pipeline ----------
def pick_input_device():
    """Prefer a real mic (BlackHole virtual devices cause -9986 errors)."""
    import sounddevice as sd
    try:
        for i, d in enumerate(sd.query_devices()):
            name = d["name"].lower()
            if d["max_input_channels"] > 0 and (
                    "microphone" in name or "macbook" in name):
                return i
    except Exception:
        pass
    return None


def start_talk():
    if recording["active"]:
        return
    import time
    print(f"[jarvis] key down → beep", flush=True)
    beep_now()  # instant, non-blocking
    events.put(("status", "LISTENING… release to send"))

    import time
    import sounddevice as sd

    def cb(indata, frames, time_info, status):
        if recording["active"]:
            recording["frames"].append(indata.copy())

    # close any stale stream from a previous talk
    try:
        recording.get("stream") and recording["stream"].close()
    except Exception:
        pass

    dev = pick_input_device()
    stream, rate, last_err = None, SAMPLE_RATE, None
    candidates = [SAMPLE_RATE]
    try:
        native = sd.query_devices(dev, "input")["default_samplerate"]
        if native != SAMPLE_RATE:
            candidates.append(native)
    except Exception:
        pass
    for r in candidates:
        try:
            kw = dict(samplerate=r, channels=1, dtype="float32",
                      callback=cb)
            if dev is not None:
                kw["device"] = dev
            stream = sd.InputStream(**kw)
            stream.start()
            rate = r
            break
        except Exception as e:
            last_err = e
            time.sleep(0.3)
    if stream is None:
        print(f"[jarvis] mic open failed: {last_err}", flush=True)
        events.put(("status", "Mic busy — release key, wait a sec, hold again"))
        return
    recording["stream"] = stream
    recording["rate"] = rate
    recording["frames"] = []
    recording["active"] = True


def stop_talk():
    if not recording["active"]:
        return
    recording["active"] = False
    try:
        recording["stream"].stop()
        recording["stream"].close()
    except Exception:
        pass
    events.put(("status", "TRANSCRIBING…"))
    threading.Thread(target=_pipeline, daemon=True).start()


def _pipeline():
    import numpy as np
    import time
    import wave
    t0 = time.time()
    if not recording["frames"]:
        events.put(("status", f"READY — hold {HOTKEY_LABEL} to talk"))
        return
    audio = np.concatenate(recording["frames"], axis=0).flatten()
    rate = recording.get("rate", SAMPLE_RATE)
    if rate != SAMPLE_RATE:  # resample device-native rate to 16k for STT
        n = int(len(audio) * SAMPLE_RATE / rate)
        audio = np.interp(np.linspace(0, len(audio), n),
                          np.arange(len(audio)), audio).astype(np.float32)
    secs = len(audio) / SAMPLE_RATE
    print(f"[jarvis] got {secs:.1f}s audio, transcribing…", flush=True)
    events.put(("status", f"TRANSCRIBING {secs:.0f}s audio…"))
    wav = str(BASE_DIR / "assets" / "_tmp.wav")
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes((audio * 32767).astype(np.int16).tobytes())
    try:
        heard = transcribe(wav)
    except Exception as e:
        print(f"[jarvis] transcribe failed: {e}", flush=True)
        events.put(("status", f"mic/model error: {e}"))
        return
    print(f"[jarvis] transcribed in {time.time()-t0:.1f}s: {heard!r}",
          flush=True)
    if not heard:
        events.put(("status", "READY — didn't catch that, try again"))
        return
    events.put(("you", heard))
    events.put(("status", "THINKING…"))
    try:
        reply, mood = think(heard)
        print(f"[jarvis] mood: {mood}", flush=True)
    except Exception as e:
        reply = f"Copy — brain error: {e}"
    events.put(("jarvis", reply))
    speak(reply)


# ---------- global hotkey (works while gaming) ----------
def hotkey_loop():
    try:
        from pynput import keyboard
        from pynput.keyboard import Key
    except Exception as e:
        events.put(("status", f"hotkey lib failed: {e} — use TALK button"))
        print(f"[jarvis] pynput import failed: {e}", flush=True)
        return
    key_map = {"alt_r": Key.alt_r, "alt_l": Key.alt_l,
               "ctrl_r": Key.ctrl_r, "ctrl_l": Key.ctrl_l,
               "f9": Key.f9, "caps_lock": Key.caps_lock}
    target = key_map.get(HOTKEY_HOLD, Key.alt_r)

    def on_press(key):
        try:
            if key == target:
                start_talk()
        except Exception as e:
            print(f"[jarvis] talk start failed: {e}", flush=True)
            events.put(("status", f"talk failed: {e}"))

    def on_release(key):
        try:
            if key == target:
                stop_talk()
        except Exception as e:
            print(f"[jarvis] talk stop failed: {e}", flush=True)

    try:
        with keyboard.Listener(on_press=on_press,
                               on_release=on_release) as listener:
            events.put(("status", f"READY — hold {HOTKEY_LABEL} to talk"))
            listener.join()
    except Exception as e:
        events.put(("status", "hotkey blocked by macOS — use TALK button. "
                    "Fix: Settings → Privacy → Input Monitoring → Terminal ON"))
        print(f"[jarvis] hotkey listener failed: {e}", flush=True)


# ---------- see-through side overlay ----------
class Overlay(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Pit-Wall Jarvis")
        self.configure(bg="black")
        self.attributes("-topmost", True)   # stays above game/other apps
        self.attributes("-alpha", 0.82)     # see-through
        self.overrideredirect(True)         # borderless side strip
        w, h = 340, 560
        x = self.winfo_screenwidth() - w - 12
        y = int((self.winfo_screenheight() - h) / 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

        head = tk.Label(self, text="≡ PIT-WALL  (drag me)   [X]",
                        bg="black", fg="#f5c518",
                        font=("Arial", 12, "bold"))
        head.pack(fill="x", padx=8, pady=(8, 2))
        head.bind("<ButtonPress-1>", self._dragstart)
        head.bind("<B1-Motion>", self._dragmove)
        # click [X] area to quit
        head.bind("<ButtonRelease-1>", self._maybe_quit)

        self.status = tk.Label(self, text=f"READY — hold {HOTKEY_LABEL} to talk",
                               bg="black", fg="#888",
                               font=("Arial", 11), wraplength=310,
                               justify="left")
        self.status.pack(fill="x", padx=10)

        self.log = tk.Text(self, bg="black", fg="white",
                           font=("Arial", 13), wrap="word",
                           relief="flat", highlightthickness=0,
                           state="disabled")
        self.log.pack(fill="both", expand=True, padx=10, pady=6)
        self.log.tag_config("you", foreground="#7ee787")
        self.log.tag_config("jarvis", foreground="#f5c518")

        talk = tk.Button(self, text="HOLD TO TALK (backup)",
                         bg="#f5c518", fg="black",
                         font=("Arial", 12, "bold"), relief="flat")
        talk.pack(fill="x", padx=10, pady=(0, 10))
        talk.bind("<ButtonPress-1>", lambda e: start_talk())
        talk.bind("<ButtonRelease-1>", lambda e: stop_talk())

        self._drag = None
        self.after(150, self._pump)

    def _dragstart(self, e):
        self._drag = (e.x, e.y)

    def _dragmove(self, e):
        if self._drag:
            self.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def _maybe_quit(self, e):
        if e.x > self.winfo_width() - 40:  # clicked [X]
            self.destroy()

    def say(self, who, text):
        self.log.configure(state="normal")
        prefix = "YOU: " if who == "you" else "PIT-WALL: "
        self.log.insert("end", prefix + text + "\n\n", who)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _pump(self):
        try:
            while True:
                kind, text = events.get_nowait()
                if kind == "status":
                    self.status.configure(text=text)
                else:
                    self.say(kind, text)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(150, self._pump)


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        # Self-test: overlay + simulated exchange, no mic/hotkey needed.
        ov = Overlay()
        ov.after(400, lambda: (events.put(("you", "who is leading?")),
                               events.put(("jarvis", think("who is leading?")[0]))))
        ov.after(600, lambda: print("GEOMETRY:", ov.winfo_geometry(),
                                    "MAPPED:", ov.winfo_ismapped()))
        ov.after(2500, ov.destroy)
        ov.mainloop()
        print("SELFTEST_DONE")
    else:
        print("=" * 52, flush=True)
        print("PIT-WALL JARVIS starting… look at the RIGHT EDGE of", flush=True)
        print("your screen for the black see-through strip.", flush=True)
        print(f"HOTKEYS: hold {HOTKEY_LABEL} to talk (works in-game),", flush=True)
        print("  release to send. Backup: hold the TALK button in the strip.", flush=True)
        print("  Quit: click [X] at the top of the strip.", flush=True)
        print(f"STT backend: {stt_backend()} "
              "(parakeet v2 if nemo installed, else whisper tiny.en).", flush=True)
        print("First talk downloads the model once, then it is offline.", flush=True)
        print("If the hotkey does nothing: macOS Settings → Privacy &", flush=True)
        print("Security → Input Monitoring → turn ON your Terminal.", flush=True)
        print("=" * 52, flush=True)
        preload_beep()
        threading.Thread(target=hotkey_loop, daemon=True).start()
        try:
            Overlay().mainloop()
        except Exception:
            import traceback
            traceback.print_exc()
            print("[jarvis] overlay crashed — paste the above in chat.",
                  flush=True)
