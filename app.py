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


async def _speak_stream(text: str):
    """Stream Edge-TTS audio straight into ffplay: first sound in ~1s
    instead of waiting for the whole file to synthesize."""
    import time
    import edge_tts
    t0 = time.time()
    comm = edge_tts.Communicate(text, TTS_VOICE)
    proc = subprocess.Popen(
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
         "-i", "pipe:0"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    first = True
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            if first:
                print(f"[jarvis] first audio after {time.time()-t0:.1f}s",
                      flush=True)
                first = False
            proc.stdin.write(chunk["data"])
    proc.stdin.close()
    proc.wait()


async def _speak_save(text: str):
    """Fallback: synthesize full file, then play (slower start)."""
    import edge_tts
    await edge_tts.Communicate(text, TTS_VOICE).save(str(REPLY_MP3))
    play(REPLY_MP3)


def speak(text: str):
    events.put(("status", "SPEAKING…"))
    try:
        print("[jarvis] speaking (streaming)…", flush=True)
        asyncio.run(_speak_stream(text))
        print("[jarvis] done speaking.", flush=True)
    except Exception as e:
        print(f"[jarvis] stream failed ({e}), trying full-file…", flush=True)
        try:
            asyncio.run(_speak_save(text))
        except Exception as e2:
            print(f"[jarvis] edge-tts failed ({e2}), offline Mac voice…",
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
    events.put(("status", "THINKING…"))
    try:
        reply, mood = think(heard)
        print(f"[jarvis] mood: {mood}", flush=True)
    except Exception as e:
        reply = f"Copy — brain error: {e}"
    # show both sides together the moment the voice starts — no dead gap
    events.put(("you", heard))
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
GOLD = "#f5c518"
GREEN = "#7ee787"
INK = "#0a0a0a"
GREY = "#888888"
CARD_W = 340


def _rr(cv, x0, y0, x1, y1, r, **kw):
    pts = [x0+r, y0, x1-r, y0, x1-r, y0, x1, y0, x1, y0+r, x1, y0+r,
           x1, y1-r, x1, y1-r, x1, y1, x1-r, y1, x1-r, y1, x0+r, y1,
           x0+r, y1, x0, y1, x0, y1-r, x0, y1-r, x0, y0+r, x0, y0+r,
           x0, y0]
    return cv.create_polygon(pts, smooth=True, **kw)


class Overlay(tk.Tk):
    """ENGINEER radio card (see mockup): latest exchange only, live timer,
    freq bars. Drag to move, hold footer to talk, right-click to quit."""

    def __init__(self):
        super().__init__()
        self.title("Engineer")
        self.configure(bg="black")
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.88)
        self.overrideredirect(True)
        x = self.winfo_screenwidth() - CARD_W - 12
        self._x = x
        self._y = int((self.winfo_screenheight() - 400) / 2)
        self.geometry(f"{CARD_W}x400+{x}+{self._y}")

        self.cv = tk.Canvas(self, bg="black", highlightthickness=0)
        self.cv.pack(fill="both", expand=True)

        self.f_head = ("Helvetica", 20, "bold italic")
        self.f_label = ("Helvetica", 10, "bold")
        self.f_msg = ("Helvetica", 15, "bold italic")
        self.f_hint = ("Helvetica", 10)
        self.f_time = ("Helvetica", 15, "bold")

        self.driver_text = "standing by…"
        self.eng_text = "Radio check. Talk to me, mate."
        self.state = "ready"       # ready|listening|thinking|speaking
        self.t0 = None             # exchange timer start
        self.elapsed = 0.0
        self._press = None         # (x, y, talking?) for drag vs hold-talk

        self.cv.bind("<ButtonPress-1>", self._down)
        self.cv.bind("<B1-Motion>", self._move)
        self.cv.bind("<ButtonRelease-1>", self._up)
        self.cv.bind("<Button-3>", lambda e: self.destroy())

        self._draw()
        self.after(120, self._tick)
        self.after(150, self._pump)

    # ----- text wrap -----
    def _wrap(self, text, px=272, max_lines=6):
        import tkinter.font as tkfont
        f = tkfont.Font(font=self.f_msg)
        words, lines, cur = text.split(), [], ""
        for wd in words:
            trial = (cur + " " + wd).strip()
            if f.measure(trial) <= px:
                cur = trial
            else:
                lines.append(cur)
                cur = wd
        lines.append(cur)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1][:60].rstrip() + "…"
        return lines

    # ----- draw (two-pass so corners stay round) -----
    def _draw(self):
        import tkinter.font as tkfont
        cv = self.cv
        W, pad = CARD_W, 14

        d_lines = self._wrap(self.driver_text)
        e_lines = self._wrap(self.eng_text)
        y = 12 + 46 + 14 + 18 + (len(d_lines) * 22 + 24) + 6 + 18
        e_top = y
        y += len(e_lines) * 22 + 24
        bars_y = y + 14
        hint_y = bars_y + 34
        h = int(max(300, min(hint_y + 32, 640)))

        cv.delete("all")
        _rr(cv, 2, 2, W-2, h-2, 18, outline=GOLD, width=2, fill=INK)

        # header: red dot + ENGINEER + timer
        y = 12
        dot = "#ff2d2d" if self.state in ("listening", "speaking") else "#5a1515"
        cv.create_oval(pad+4, y+10, pad+20, y+26, fill=dot, outline="")
        cv.create_text(pad+28, y+4, text="ENGINEER", font=self.f_head,
                       fill="white", anchor="nw")
        mm, ss = divmod(int(self.elapsed), 60)
        cv.create_text(W-pad, y+8, text=f"{mm}:{ss:02d}", font=self.f_time,
                       fill=GREY, anchor="ne")
        y += 46
        cv.create_line(pad, y, W-pad, y, fill=GOLD, width=2)
        y += 14

        y = self._bubble_lines("DRIVER", d_lines, GREEN, y, pad, W)
        y += 6
        y = self._bubble_lines("ENGINEER", e_lines, GOLD, y, pad, W)

        # footer: freq bars + hint
        self._bars_y = bars_y
        n, bw, gap = 32, 5, 4
        x0 = (W - (n * (bw + gap) - gap)) / 2
        self._bar_ids, self._bar_x = [], []
        for i in range(n):
            x = x0 + i * (bw + gap)
            self._bar_x.append(x)
            self._bar_ids.append(
                cv.create_line(x, bars_y+26, x, bars_y+26,
                               fill=GOLD, width=bw))
        cv.create_text(W/2, hint_y, text=f"hold {HOTKEY_LABEL} to talk",
                       font=self.f_hint, fill=GREY)

        self._footer_top = bars_y - 6
        self.geometry(f"{CARD_W}x{h}+{self._x}+{self._y}")
        cv.configure(height=h)
        self._paint_bars(static=True)

    def _bubble_lines(self, who, lines, color, y, pad, W):
        cv = self.cv
        cv.create_text(pad+4, y, text=who, font=self.f_label, fill=GREY,
                       anchor="nw")
        y += 18
        bh = len(lines) * 22 + 24
        _rr(cv, pad, y, W-pad, y+bh, 12, outline=GOLD, width=1.5, fill=INK)
        ty = y + 12
        for ln in lines:
            cv.create_text(pad+14, ty, text=ln, font=self.f_msg,
                           fill=color, anchor="nw")
            ty += 22
        return y + bh

    def _bubble(self, who, text, color, y, pad, W):
        return self._bubble_lines(who, self._wrap(text), color, y, pad, W)

    # ----- freq bars -----
    def _paint_bars(self, static=False):
        import math
        import random
        energy = {"listening": 1.0, "speaking": 0.9, "thinking": 0.45,
                  "ready": 0.07}.get(self.state, 0.07)
        yb = self._bars_y + 26
        for i, (bid, x) in enumerate(zip(self._bar_ids, self._bar_x)):
            wave = (0.5 + 0.5 * math.sin(i * 0.7)) if static \
                else random.random()
            self.cv.coords(bid, x, yb, x, yb - (2 + wave * 26 * energy))

    # ----- loops -----
    def _tick(self):
        import time
        if self.t0 is not None:
            self.elapsed = time.time() - self.t0
        self._draw_header_only()
        self._paint_bars()
        if self.winfo_exists():
            self.after(120, self._tick)

    def _draw_header_only(self):
        # cheap refresh: full redraw is fine at 8fps for this tiny card
        pos = self.geometry().split("+", 1)[1]
        xs, ys = pos.split("+")[0], pos.split("+")[1]
        self._x, self._y = int(xs), int(ys)
        self._draw()

    def _pump(self):
        import time
        try:
            while True:
                kind, text = events.get_nowait()
                if kind == "status":
                    s = text
                    if s.startswith("LISTENING"):
                        self.state, self.t0 = "listening", time.time()
                    elif s.startswith("TRANSCRIBING") or s.startswith("THINKING"):
                        self.state = "thinking"
                    elif s.startswith("SPEAKING"):
                        self.state = "speaking"
                    elif s.startswith("READY"):
                        self.state, self.t0 = "ready", None
                        self.elapsed = 0.0
                elif kind == "you":
                    self.driver_text = text
                elif kind == "jarvis":
                    self.eng_text = text
                self._draw()
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(150, self._pump)

    # ----- mouse: drag anywhere, hold footer to talk, right-click quits -----
    def _down(self, e):
        self._press = [e.x, e.y, False]
        if e.y >= getattr(self, "_footer_top", 10**9):
            self._press[2] = True
            start_talk()

    def _move(self, e):
        if not self._press:
            return
        dx, dy = e.x - self._press[0], e.y - self._press[1]
        if abs(dx) + abs(dy) > 6 and self._press[2]:
            self._press[2] = False  # turned into a drag: cancel talk
            try:
                stop_talk()
            except Exception:
                pass
        if not self._press[2]:
            self.geometry(f"+{e.x_root - self._press[0]}+{e.y_root - self._press[1]}")

    def _up(self, e):
        if self._press and self._press[2]:
            try:
                stop_talk()
            except Exception:
                pass
        self._press = None


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        # Self-test: overlay + simulated exchange, no mic/hotkey needed.
        ov = Overlay()
        ov.after(300, lambda: events.put(("status", "LISTENING… release to send")))
        ov.after(400, lambda: (events.put(("you", "who is leading?")),
                               events.put(("jarvis", think("who is leading?")[0]))))
        ov.after(500, lambda: events.put(("status", "SPEAKING…")))
        ov.after(1200, lambda: events.put(
            ("status", f"READY — hold {HOTKEY_LABEL} to talk")))
        ov.after(600, lambda: print("GEOMETRY:", ov.winfo_geometry(),
                                    "MAPPED:", ov.winfo_ismapped()))
        ov.after(2500, ov.destroy)
        ov.mainloop()
        print("SELFTEST_DONE")
    else:
        print("=" * 52, flush=True)
        print("ENGINEER starting… look at the RIGHT EDGE of your screen", flush=True)
        print("for the black + gold radio card.", flush=True)
        print(f"HOTKEYS: hold {HOTKEY_LABEL} to talk (works in-game),", flush=True)
        print("  release to send. Backup: hold the card footer.", flush=True)
        print("  Drag card to move. Right-click card to quit.", flush=True)
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
