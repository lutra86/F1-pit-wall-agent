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

from brain import think  # Aussie + mood mirror brain (needs openai pkg)

BASE_DIR = Path(__file__).parent
PORT = 8765

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
            reply, mood = think(text)
            self._json({"reply": reply, "mood": mood})
            return
        reply, mood = think(text)
        self._json({"reply": reply, "mood": mood})

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
