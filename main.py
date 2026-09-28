"""F1 Jarvis — push-to-talk, inspired by sloganking/quick-assistant.
Flow: press ENTER (or hold SPACE later) -> F1 radio beep -> listen ->
NVIDIA LLM (OpenAI-compatible, free tier) -> Edge-TTS (free) speaks back.

Setup:
  pip install -r requirements.txt
  cp .env.example .env   # put NVIDIA_API_KEY from build.nvidia.com
  python main.py
"""
import os
import re
import asyncio
import subprocess
from pathlib import Path

import speech_recognition as sr
import edge_tts
from openai import OpenAI
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import tools_mac as mac
import tools_f1 as f1

BASE_DIR = Path(__file__).parent
BEEP = BASE_DIR / "assets" / "beep.mp3"
OUT = BASE_DIR / "assets" / "reply.mp3"

SYSTEM = ("You are Pit-Wall Jarvis, an F1 race engineer. "
          "Short radio replies, max 2 sentences. Start key info with 'Copy. '. "
          "You can control volume/media/apps/brightness and read F1 timing. "
          "If user asks to write something, confirm what you wrote.")

def client():
    return OpenAI(base_url="https://integrate.api.nvidia.com/v1",
                  api_key=os.getenv("NVIDIA_API_KEY"))

def play(path: Path):
    subprocess.run(["afplay", str(path)], capture_output=True)

async def speak(text: str):
    voice = os.getenv("TTS_VOICE", "en-GB-RyanNeural")
    await edge_tts.Communicate(text, voice).save(str(OUT))
    play(OUT)

def listen_once() -> str:
    r = sr.Recognizer()
    with sr.Microphone() as src:
        print("...listening (speak now, 8s max)...")
        audio = r.listen(src, timeout=5, phrase_time_limit=8)
    try:
        return r.recognize_google(audio)
    except sr.UnknownValueError:
        return ""

def route(text: str) -> str | None:
    """Local tool routing like quick-assistant. Returns handled reply or None."""
    t = text.lower()
    m = re.search(r"volume.*?(\d+)", t)
    if "volume" in t and m:
        return mac.set_volume(int(m.group(1)))
    if any(k in t for k in ("brightness", "dim", "bright")):
        m2 = re.search(r"(\d+)", t)
        lvl = int(m2.group(1)) if m2 else 70
        return mac.set_brightness(lvl)
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
    m4 = re.search(r"car (\d+).*lap|lap.*car (\d+)|driver (\d+)", t)
    if m4:
        num = next(g for g in m4.groups() if g)
        return "Copy. " + f1.driver_laps(int(num))
    if text.lower().startswith("write ") or "write file" in t:
        p = BASE_DIR / "note.txt"
        p.write_text(text)
        return f"Copy, written to {p.name}."
    return None

def ask_llm(text: str) -> str:
    c = client()
    resp = c.chat.completions.create(
        model=os.getenv("NVIDIA_MODEL", "meta/llama-3.2-11b-vision-instruct"),
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": text}],
        max_tokens=150, temperature=0.6)
    return resp.choices[0].message.content.strip()

def main():
    if not os.getenv("NVIDIA_API_KEY"):
        print("Missing NVIDIA_API_KEY. cp .env.example .env and add key from build.nvidia.com")
        return
    print("F1 JARVIS ready. Press ENTER to talk (your button), 'q' to quit.")
    while True:
        cmd = input("> ENTER=talk | q=quit: ").strip()
        if cmd.lower() == "q":
            break
        play(BEEP)  # your F1 radio beep
        heard = listen_once()
        if not heard:
            print("Didn't catch that, say again.")
            continue
        print(f"You: {heard}")
        handled = route(heard)
        reply = handled if handled else ask_llm(heard)
        print(f"Jarvis: {reply}")
        asyncio.run(speak(reply))

if __name__ == "__main__":
    main()
