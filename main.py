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

import tools_mac as mac  # noqa: F401 (kept for CLI tinkering)
import tools_f1 as f1  # noqa: F401
from brain import think, route, ask_llm  # Aussie + mood mirror brain

BASE_DIR = Path(__file__).parent
BEEP = BASE_DIR / "assets" / "beep.mp3"
OUT = BASE_DIR / "assets" / "reply.mp3"

def client():
    return OpenAI(base_url="https://integrate.api.nvidia.com/v1",
                  api_key=os.getenv("NVIDIA_API_KEY"))

def play(path: Path):
    subprocess.run(["afplay", str(path)], capture_output=True)

async def speak(text: str):
    voice = os.getenv("TTS_VOICE", "en-AU-WilliamMultilingualNeural")
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
        reply, mood = think(heard)
        print(f"Jarvis [{mood}]: {reply}")
        asyncio.run(speak(reply))

if __name__ == "__main__":
    main()
