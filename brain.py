"""Shared brain: Aussie pit-wall personality, mood mirror, tools, NVIDIA LLM."""
import os
import re
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import tools_mac as mac
import tools_f1 as f1
import tools_web as web
import tools_files as desk

BASE_DIR = Path(__file__).parent
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.2-11b-vision-instruct")

SYSTEM_AUSSIE = (
    "You are Pit-Wall Jarvis, an Aussie F1 race engineer on the pit wall. "
    "Talk like one: 'copy', 'mate', 'send it', 'box box', 'she'll be right'. "
    "Short radio replies, max 2 sentences. Start key info with 'Copy. '. "
    "You can control volume/media/apps/brightness and read F1 timing. "
    "You can search the web, read pages, and manage files in the workspace. "
    "If asked to write something, confirm what you wrote. "
    "Never bluff: if the provided info doesn't cover the question, say "
    "'no data on that one, mate' instead of guessing.")

MOOD_CHILL = ("The driver is calm and friendly. Match it: warm, encouraging "
              "Aussie race-engineer, light slang, no swearing.")
MOOD_FERAL = ("The driver is blowing up — angry, swearing, giving you both "
              "barrels. Mirror them exactly: swear back naturally like a "
              "filthy-mouthed Aussie pit crew — say fuck, shit, bloody, "
              "bugger in your reply, at least two swear words, no asterisks, "
              "no lecture, no apology for language. Blunt pit-wall talk. "
              "Still answer the actual question underneath the spray.")

SWEARS = ["fuck", "shit", "cunt", "bitch", "asshole", "arsehole", "dick",
          "bastard", "wanker", "prick", "bullshit", "bloody hell"]

# Local feral spray: the LLM is safety-tuned and dodges swearing, so when
# the driver is feral we bolt real pit-wall spray onto the reply ourselves.
# Rotates so it doesn't sound canned.
FERAL_OPENERS = [
    "Oi, pull your fucking head in. ",
    "Fuck me, listen for once. ",
    "Right, quit your bitching and listen. ",
    "Shit, mate, calm the fuck down. ",
]
_feral_n = 0


def feral_wrap(reply: str) -> str:
    global _feral_n
    if any(w in reply.lower() for w in SWEARS):
        return reply
    opener = FERAL_OPENERS[_feral_n % len(FERAL_OPENERS)]
    _feral_n += 1
    return opener + reply


def detect_mood(text: str) -> str:
    """feral if swearing/shouting, else chill."""
    t = text.lower()
    if any(w in t for w in SWEARS):
        return "feral"
    shout = text.count("!") >= 2 or (text.isupper() and len(text) > 8)
    if shout:
        return "feral"
    return "chill"


def ask_llm(text: str, mood: str = "chill", context: str = "") -> str:
    from openai import OpenAI
    c = OpenAI(base_url="https://integrate.api.nvidia.com/v1",
               api_key=os.getenv("NVIDIA_API_KEY"), timeout=30)
    system = SYSTEM_AUSSIE + " " + (MOOD_FERAL if mood == "feral"
                                    else MOOD_CHILL)
    msgs = [{"role": "system", "content": system}]
    if context:
        msgs.append({"role": "user",
                     "content": "Live web info for my next question "
                                f"(use it, stay short): {context}"})
    msgs.append({"role": "user", "content": text})
    resp = c.chat.completions.create(
        model=NVIDIA_MODEL, messages=msgs,
        max_tokens=80, temperature=0.8 if mood == "feral" else 0.6)
    return resp.choices[0].message.content.strip()


LIVE_HINTS = ("latest", "now", "today", "tonight", "current", "live",
              "score", "standing", "winner", "who won", "news", "weather",
              "happening", "result")

F1_WORDS = ("f1", "formula 1", "formula one", "grand prix", "verstappen",
            "norris", "piastri", "russell", "leclerc", "hamilton", "alonso",
            "tsunoda", "antonelli", "bearman", "hadjar", "mclaren", "ferrari",
            "red bull", "mercedes", "williams", "alpine", "aston martin",
            "sauber", "rb ", "drs", "pit stop", "pole", "qualifying",
            "podium", "championship", "constructor", "safety car", "box box",
            "tyre", "tire", "downforce", "understeer", "oversteer", "paddock",
            "team radio", "driver", "lap")


def looks_live(text: str) -> bool:
    t = text.lower()
    return any(h in t for h in LIVE_HINTS)


def looks_f1(text: str) -> bool:
    t = " " + text.lower() + " "
    return any(w in t for w in F1_WORDS)


def model_check() -> str:
    """Report the active brain model + live ping."""
    from openai import OpenAI
    try:
        c = OpenAI(base_url="https://integrate.api.nvidia.com/v1",
                   api_key=os.getenv("NVIDIA_API_KEY"), timeout=20)
        r = c.chat.completions.create(
            model=NVIDIA_MODEL,
            messages=[{"role": "user", "content": "Reply with: online"}],
            max_tokens=5)
        heard = r.choices[0].message.content.strip()
        return (f"Copy, running {NVIDIA_MODEL}, online — it said '{heard}'. "
                f"Knowledge frozen at training, so I use live tools + web "
                f"for anything current.")
    except Exception as e:
        return (f"Copy, configured {NVIDIA_MODEL} but it's not answering: "
                f"{str(e)[:100]}")


def route(text: str, mood: str = "chill"):
    """Local tools. Feral mood gets matching pit-wall spray."""
    t = text.lower()
    f = (mood == "feral")
    if any(k in t for k in ("which model", "what model", "model check",
                            "are you running", "muse spark")):
        return model_check()
    m = re.search(r"volume.*?(\d+)", t)
    if "volume" in t and m:
        base = mac.set_volume(int(m.group(1)))
        return (base + " Now quit yelling, ya drongo." if f else base)
    if any(k in t for k in ("brightness", "dim", "bright")):
        m2 = re.search(r"(\d+)", t)
        return mac.set_brightness(int(m2.group(1)) if m2 else 70)
    if any(k in t for k in ("pause", "play music", "next track", "previous")):
        act = "next" if "next" in t else ("prev" if "prev" in t else "play")
        return mac.media(act)
    m3 = re.search(r"open (\w+)", t)
    if m3:
        return mac.open_app(m3.group(1).capitalize())
    if any(k in t for k in ("championship", "standings", "constructor")):
        return "Copy. " + f1.championship()
    if "position" in t or "who is leading" in t:
        r = "Copy. " + f1.session_positions()
        return (r + " Happy now?" if f else r)
    if "weather" in t or "track temp" in t:
        return "Copy. " + f1.weather()
    if "latest session" in t or "what race" in t:
        return "Copy. " + f1.latest_session_info()
    m4 = re.search(r"car (\d+).*lap|lap.*car (\d+)|driver (\d+)", t)
    if m4:
        num = next(g for g in m4.groups() if g)
        return "Copy. " + f1.driver_laps(int(num))
    m6 = re.search(r"(read|open) (page|site|url|link) (\S+)", t)
    if m6:
        return "Copy. " + web.read_page(m6.group(3))
    if "list files" in t or "what files" in t or "show files" in t:
        return "Copy. " + desk.list_files()
    m7 = re.search(r"read file (\S+)", t)
    if m7:
        return desk.read_file(m7.group(1))
    m8 = re.search(r"write file (\S+)\s*[:\-]?\s*(.*)", t)
    if m8:
        name = m8.group(1).rstrip(":")
        content = m8.group(2).strip() or text
        return desk.write_file(name, content)
    if t.startswith("write ") or "write file" in t:
        return desk.write_file("note.txt", text)
    return None


def think(text: str):
    """Returns (reply, mood). Full pipeline: tools first, LLM second."""
    import time
    mood = detect_mood(text)
    handled = route(text, mood)
    if handled:
        return handled, mood
    if not os.getenv("NVIDIA_API_KEY"):
        return ("Copy — I heard you, mate, but add NVIDIA_API_KEY to .env "
                "for full answers. Local tools already work."), mood
    t0 = time.time()
    m5 = re.search(r"(search|google|look up|look-up|find out)( for)? (.+)",
                   text.lower())
    parts = []
    if looks_f1(text):  # every F1 question gets 2026 paddock reality
        parts.append("Paddock now: " + f1.live_brief())
    if m5:
        parts.append(web.web_search(m5.group(3), n=5))
    elif looks_live(text):
        parts.append(web.web_search(text, n=5))
    ctx = " ".join(parts)
    reply = ask_llm(text, mood, context=ctx)
    print(f"[jarvis] brain took {time.time()-t0:.1f}s", flush=True)
    if mood == "feral":
        reply = feral_wrap(reply)
    return reply, mood
