"""Pit-wall tools — free OpenF1 historical data, no key needed.
Live data needs a sponsor sub (€9.90/mo), so we default to latest/historical."""
import requests

BASE = "https://api.openf1.org/v1"

def latest_session_info() -> str:
    try:
        r = requests.get(f"{BASE}/sessions", params={"session_key": "latest"}, timeout=10)
        r.raise_for_status()
        s = r.json()[0]
        return (f"{s.get('session_name')} — {s.get('location')} {s.get('year')} "
                f"({s.get('date_start')}). Key {s.get('session_key')}.")
    except Exception as e:
        return f"Telemetry unavailable: {e}"

def session_positions(session_key: str = "latest", top_n: int = 5) -> str:
    """Top-N by position endpoint."""
    try:
        r = requests.get(f"{BASE}/position",
                         params={"session_key": session_key}, timeout=10)
        r.raise_for_status()
        rows = r.json()
        latest = {}
        for row in rows:
            latest[row["driver_number"]] = row["position"]
        ordered = sorted(latest.items(), key=lambda x: x[1])[:top_n]
        return "Positions: " + ", ".join(f"#{p} car {d}" for d, p in ordered)
    except Exception as e:
        return f"Timing unavailable: {e}"

def driver_laps(driver_number: int, session_key: str = "latest", limit: int = 3) -> str:
    try:
        r = requests.get(f"{BASE}/laps",
                         params={"session_key": session_key,
                                 "driver_number": driver_number}, timeout=10)
        r.raise_for_status()
        laps = r.json()[-limit:]
        out = [f"L{l['lap_number']} {l.get('lap_duration')}" for l in laps]
        return f"Car {driver_number} last laps: " + ", ".join(out)
    except Exception as e:
        return f"Lap data unavailable: {e}"

def weather(session_key: str = "latest") -> str:
    try:
        r = requests.get(f"{BASE}/weather",
                         params={"session_key": session_key}, timeout=10)
        r.raise_for_status()
        w = r.json()[-1]
        return (f"Track {w.get('track_temperature')}C, air {w.get('air_temperature')}C, "
                f"humidity {w.get('humidity')}%, rain {w.get('rainfall')}.")
    except Exception as e:
        return f"Weather unavailable: {e}"


def championship(top_n: int = 3) -> str:
    """Real drivers' championship standings (constructors endpoint is down)."""
    try:
        r = requests.get(f"{BASE}/championship_drivers",
                         params={"session_key": "latest"}, timeout=10)
        r.raise_for_status()
        rows = sorted(r.json(), key=lambda x: x["position_current"])[:top_n]
        d = requests.get(f"{BASE}/drivers",
                         params={"session_key": "latest"},
                         timeout=10).json()
        names = {x["driver_number"]: x["broadcast_name"] for x in d}
        bits = [f"{names.get(x['driver_number'], 'car '+str(x['driver_number']))} "
                f"{x['points_current']}pts" for x in rows]
        return "Championship: " + ", ".join(bits)
    except Exception as e:
        return f"Championship unavailable: {e}"


JOLPI = "https://api.jolpi.ca/ergast/f1"  # free Ergast mirror, no key


def _jolpi(path: str):
    import json
    import urllib.request
    with urllib.request.urlopen(JOLPI + path, timeout=12) as r:
        return json.loads(r.read())["MRData"]


def last_race() -> str:
    """Official last-race result: winner + podium."""
    try:
        race = _jolpi("/current/last/results.json")["RaceTable"]["Races"][0]
        top = [f"{x['position']}. {x['Driver']['code']} "
               f"({x['Constructor']['name']})"
               for x in race["Results"][:3]]
        return f"Last race, {race['raceName']} {race['season']}: " + ", ".join(top)
    except Exception as e:
        return f"Last race unavailable: {str(e)[:80]}"


def season_table(top_n: int = 3) -> str:
    """Official drivers' standings."""
    try:
        lst = _jolpi("/current/driverStandings.json")["StandingsTable"][
            "StandingsLists"][0]["DriverStandings"][:top_n]
        bits = [f"{d['Driver']['code']} {d['points']}pts" for d in lst]
        return "Standings: " + ", ".join(bits)
    except Exception as e:
        return championship(top_n)  # OpenF1 fallback


def next_race() -> str:
    try:
        from datetime import date
        sched = _jolpi("/current.json")["RaceTable"]["Races"]
        upcoming = [r for r in sched if r["date"] >= str(date.today())]
        if not upcoming:
            return "Season's done, mate."
        r = upcoming[0]
        return f"Next up: {r['raceName']} on {r['date']}."
    except Exception as e:
        return f"Schedule unavailable: {str(e)[:80]}"


def live_brief() -> str:
    """One-block 2026 reality check for the LLM: latest session + order."""
    try:
        return (latest_session_info() + " || " +
                session_positions(top_n=5) + " || " + weather() + " || " +
                last_race())
    except Exception as e:
        return f"Paddock feed down: {e}"
