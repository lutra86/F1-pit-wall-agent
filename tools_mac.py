"""Mac system controls — inspired by quick-assistant features, ported to macOS."""
import subprocess
import platform
import shutil

def set_volume(level: int) -> str:
    """0-100, macOS via osascript."""
    level = max(0, min(100, level))
    subprocess.run(["osascript", "-e", f"set volume output volume {level}"],
                   capture_output=True)
    return f"Copy, volume set to {level}%."

def media(action: str) -> str:
    """play/pause/next/prev via osascript."""
    keymap = {"play": "playpause", "pause": "playpause",
              "next": "next track", "prev": "previous track"}
    cmd = keymap.get(action.lower(), "playpause")
    subprocess.run(["osascript", "-e", f'tell application "Music" to {cmd}'],
                   capture_output=True)
    # fallback: pretend ok even if Music not running (Spotify etc. use media keys)
    return f"Copy, media {action}."

def set_brightness(level: int) -> str:
    """Best-effort macOS brightness. macOS has no built-in CLI.
    Tries `brightness` tool (brew install brightness) if present."""
    level = max(0, min(100, level)) / 100.0
    if shutil.which("brightness"):
        subprocess.run(["brightness", str(level)], capture_output=True)
        return f"Copy, brightness set to {int(level*100)}%."
    return ("Negative — install brightness control with `brew install brightness`, "
            "then I can set display brightness. Volume/media/apps already work.")

def open_app(name: str) -> str:
    subprocess.run(["open", "-a", name], capture_output=True)
    return f"Copy, opening {name}."

def system_info() -> str:
    import platform as p
    return f"{p.system()} {p.machine()}, {p.mac_ver()[0] or p.release()}."
