"""Scoped computer access — files live ONLY inside the workspace dir.

Nothing outside JARVIS_HOME can be read, written, or listed. Path
traversal (.. , absolute paths) is rejected.
"""
import os
from pathlib import Path

HOME = Path(os.getenv("JARVIS_HOME",
                      Path.home() / "Documents" / "f1-jarvis-files"))
HOME.mkdir(parents=True, exist_ok=True)


def _safe(name: str) -> Path | None:
    p = (HOME / name).resolve()
    if p == HOME or str(p).startswith(str(HOME) + os.sep):
        return p
    return None


def list_files() -> str:
    files = sorted(f.name for f in HOME.iterdir() if f.is_file())
    return ("Workspace empty. Ask me to write something." if not files
            else "Files: " + ", ".join(files))


def read_file(name: str) -> str:
    p = _safe(name.strip())
    if not p or not p.is_file():
        return f"Copy — no file '{name}' in the workspace."
    try:
        return f"{p.name}: " + p.read_text()[:2000]
    except Exception as e:
        return f"Could not read '{name}': {str(e)[:80]}"


def write_file(name: str, text: str) -> str:
    p = _safe(name.strip())
    if not p:
        return "Negative — that path is outside the workspace."
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return f"Copy, written to {p.name}."
    except Exception as e:
        return f"Could not write '{name}': {str(e)[:80]}"
