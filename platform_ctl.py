"""One API for system controls on macOS / Windows / Linux.

Same function names everywhere; each OS gets its own backend.
Needs ffmpeg on PATH for mp3 playback outside macOS.
"""
import os
import platform
import shutil
import subprocess

OS = platform.system()  # Darwin | Windows | Linux


def _run(*args):
    return subprocess.run(list(args), capture_output=True)


# ---------- audio playback ----------
def play_audio(path) -> bool:
    """Play an mp3/wav file. Returns True if something played it."""
    path = str(path)
    if OS == "Darwin":
        _run("afplay", path)
        return True
    if shutil.which("ffplay"):
        _run("ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
             "-i", path)
        return True
    if OS == "Windows" and path.endswith(".wav"):
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME)
        return True
    return False


# ---------- volume ----------
def set_volume(level: int) -> str:
    level = max(0, min(100, int(level)))
    if OS == "Darwin":
        _run("osascript", "-e", f"set volume output volume {level}")
        return f"Copy, volume set to {level}%."
    if OS == "Windows":
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            dev = AudioUtilities.GetSpeakers()
            vol = cast(dev.Activate(IAudioEndpointVolume._iid_,
                                    CLSCTX_ALL, None),
                       POINTER(IAudioEndpointVolume))
            vol.SetMasterVolumeLevelScalar(level / 100, None)
            return f"Copy, volume set to {level}%."
        except Exception:
            return ("Negative — pip install pycaw for Windows volume, "
                    "mate.")
    # Linux
    if shutil.which("amixer"):
        _run("amixer", "-q", "set", "Master", f"{level}%")
        return f"Copy, volume set to {level}%."
    if shutil.which("pactl"):
        _run("pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%")
        return f"Copy, volume set to {level}%."
    return "Negative — no mixer found (need amixer or pactl)."


# ---------- media keys ----------
def media(action: str) -> str:
    action = action.lower()
    if OS == "Darwin":
        keymap = {"play": "playpause", "pause": "playpause",
                  "next": "next track", "prev": "previous track"}
        _run("osascript", "-e",
             f'tell application "Music" to {keymap.get(action, "playpause")}')
        return f"Copy, media {action}."
    if OS == "Windows":
        from pynput.keyboard import Key, Controller
        kb = Controller()
        keys = {"play": Key.media_play_pause, "pause": Key.media_play_pause,
                "next": Key.media_next, "prev": Key.media_previous}
        k = keys.get(action, Key.media_play_pause)
        kb.press(k)
        kb.release(k)
        return f"Copy, media {action}."
    if shutil.which("playerctl"):
        _run("playerctl",
             {"play": "play-pause", "pause": "play-pause"}.get(action, action))
        return f"Copy, media {action}."
    return "Negative — pip install playerctl for Linux media keys."


# ---------- brightness ----------
def set_brightness(level: int) -> str:
    lvl = max(0, min(100, int(level)))
    if OS == "Darwin":
        if shutil.which("brightness"):
            _run("brightness", str(lvl / 100))
            return f"Copy, brightness set to {lvl}%."
        return ("Negative — `brew install brightness` first, then I can "
                "dim the screen.")
    if OS == "Linux":
        for cmd in (["brightnessctl", "set", f"{lvl}%"],
                    ["xbacklight", "-set", str(lvl)]):
            if shutil.which(cmd[0]):
                _run(*cmd)
                return f"Copy, brightness set to {lvl}%."
        return "Negative — need brightnessctl or xbacklight."
    return "Negative — brightness needs a vendor tool on Windows."


# ---------- apps ----------
def open_app(name: str) -> str:
    if OS == "Darwin":
        _run("open", "-a", name)
    elif OS == "Windows":
        os.startfile(name)  # type: ignore[attr-defined]
    elif shutil.which(name):
        subprocess.Popen([name], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    elif shutil.which("gtk-launch"):
        subprocess.Popen(["gtk-launch", name.lower()],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        return f"Negative — can't find app '{name}'."
    return f"Copy, opening {name}."


# ---------- info ----------
def system_info() -> str:
    return (f"{platform.system()} {platform.release()} "
            f"{platform.machine()}, Python {platform.python_version()}")


# ---------- offline voice (last-resort fallback) ----------
def offline_say(text: str) -> bool:
    if OS == "Darwin":
        _run("say", text)
        return True
    if shutil.which("espeak-ng"):
        _run("espeak-ng", text)
        return True
    if OS == "Windows":
        _run("powershell", "-Command",
             f'Add-Type -AssemblyName System.Speech; '
             f'(New-Object System.Speech.Synthesis.SpeechSynthesizer)'
             f'.Speak("{text[:200]}")')
        return True
    return False


def default_hotkey() -> str:
    if OS == "Darwin":
        return "alt_r"   # Right Option
    return "f9"          # safe on Windows/Linux
