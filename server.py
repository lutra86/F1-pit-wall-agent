"""F1 Jarvis side-panel server (stdlib only).
Serves radio_wall.html + /api/ask (reuses tools + NVIDIA LLM).
Use with Handy: hold your Handy hotkey while the Ask box is focused,
speak, release — Handy pastes the text, hit Ask.

Run: python server.py   -> open http://localhost:8765
"""
import json
import os
import urllib.parse
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import tools_mac as mac
import tools_f1 as f1

BASE_DIR = Path(__file__).parent
PORT = 8765

SYSTEM = ("You are Pit-Wall Jarvis, an F1 race engineer. "
          "Short radio replies, max 2 sentences. Start with 'Copy. '.")

def ask_llm(text: str) -> str:
    from openai import OpenAI
    c = OpenAI(base_url="https://integrate.api.nvidia.com/v1",
               api_key=os.getenv("NVIDIA_API_KEY"))
    resp = c.chat.completions.create(
        model=os.getenv("NVIDIA_MODEL", "meta/llama-3.2-11b-vision-instruct"),
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": text}],
        max_tokens=150, temperature=0.6)
    return resp.choices[0].message.content.strip()

# local routing (same rules as main.py, stdlib-only so no heavy deps needed)
import re

def route(text: str):
    t = text.lower()
    m = re.search(r"volume.*?(\d+)", t)
    if "volume" in t and m:
        return mac.set_volume(int(m.group(1)))
    if any(k in t for k in ("brightness", "dim", "bright")):
        m2 = re.search(r"(\d+)", t)
        return mac.set_brightness(int(m2.group(1)) if m2 else 70)
    if any(k in t for k in ("pause", "play music", "next track", "previous")):
        act = "next" if "next" in t else ("prev" if "prev" in t else "play")
        return mac.media(act)
    m3 = re.search(r"open (\w+)", t)
    if m3:
        return mac.open_app(m3.group(1).capitalize())
    if "position" in t or "standings" in t or "who is leading" in t:
        return "Copy. " + f1.session_positions()
    if "weather" in t or "track temp" in t:
        return "Copy. " + f1.weather()
    if "latest session" in t or "what race" in t:
        return "Copy. " + f1.latest_session_info()
    return None

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/radio"):
            self.path = "/radio_wall.html"
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/ask":
            self.send_error(404); return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        text = body.get("text", "").strip()
        if not text:
            self._json({"reply": "Say again, driver?"})
            return
        if not os.getenv("NVIDIA_API_KEY"):
            handled = route(text)
            self._json({"reply": handled or
                        "Copy — add NVIDIA_API_KEY in .env for full brain, "
                        "but radio wall + local tools already work."})
            return
        handled = route(text)
        reply = handled if handled else ask_llm(text)
        self._json({"reply": reply})

    def _json(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass

if __name__ == "__main__":
    os.chdir(BASE_DIR)
    print(f"Pit wall up: http://localhost:{PORT}  (dock it on the side)")
    print("Handy tip: focus the Ask box, hold your Handy hotkey, speak, release.")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
