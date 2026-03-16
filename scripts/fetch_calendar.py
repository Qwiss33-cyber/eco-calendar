#!/usr/bin/env python3
"""
EcoNews Live - Smart Calendar Fetcher
Laeuft alle 5 Min via GitHub Actions.
"""

import json, os, sys, glob
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, "data")
ARCHIVE_DIR = os.path.join(DATA_DIR, "archive")
OUT_FILE = os.path.join(DATA_DIR, "calendar.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

now = datetime.now(timezone.utc)


def load_current_events():
    if not os.path.exists(OUT_FILE):
        return []
    try:
        with open(OUT_FILE, "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return data.get("events", [])
    except:
        return []


def is_weekend():
    weekday = now.weekday()
    if weekday == 6 and now.hour < 22:
        return True
    if weekday == 5 and now.hour >= 22:
        return True
    return False


def need_actual_fetch(events):
    cutoff = now - timedelta(minutes=6)
    for evt in events:
        try:
            evt_time = datetime.fromisoformat(evt.get("date", "").replace("Z", "+00:00"))
            if evt_time.tzinfo is None:
                evt_time = evt_time.replace(tzinfo=timezone.utc)
            impact = (evt.get("impact") or "").lower()
            if ("high" in impact or "medium" in impact) and cutoff <= evt_time <= now:
                if not (evt.get("actual") or ""):
                    print(f"[ACTUAL] {evt.get('country','')} {evt.get('title','')}")
                    return True
        except:
            continue
    return False


def need_regular_fetch():
    if not os.path.exists(OUT_FILE):
        print("[FETCH] Keine Datei")
        return True
    current = load_current_events()
    if not current:
        print("[FETCH] Events leer")
        return True
    try:
        with open(OUT_FILE, "r") as f:
            data = json.load(f)
        updated = data.get("meta", {}).get("updated_utc", "")
        if not updated:
            print("[FETCH] Kein Timestamp")
            return True
        last = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        age = (now - last).total_seconds() / 60
        if age > 60:
            print(f"[FETCH] Daten {int(age)} Min alt")
            return True
    except:
        print("[FETCH] Fehler beim Lesen")
        return True
    return False


def fetch_ff():
    try:
        req = Request(FF_URL, headers={"User-Agent": UA})
        with urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        print(f"[OK] {len(data)} Events geholt")
        return data
    except HTTPError as e:
        print(f"[ERR] HTTP {e.code}")
        return None
    except Exception as e:
        print(f"[ERR] {e}")
        return None


def get_week_key(dt=None):
    return (dt or now).strftime("%Y_W%V")


def archive_week(events):
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    key = get_week_key()
    with open(os.path.join(ARCHIVE_DIR, f"{key}.json"), "w") as f:
        json.dump(events, f)
    print(f"[ARCHIV] {key}: {len(events)} Events")


def load_last_week():
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    key = get_week_key(now - timedelta(weeks=1))
    path = os.path.join(ARCHIVE_DIR, f"{key}.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []


def cleanup():
    files = sorted(glob.glob(os.path.join(ARCHIVE_DIR, "*.json")))
    for f in files[:-4]:
        os.remove(f)


def save(this_week, last_week, reason):
    os.makedirs(DATA_DIR, exist_ok=True)
    combined = last_week + this_week
    with open(OUT_FILE, "w") as f:
        json.dump({
            "meta": {
                "source": "ForexFactory",
                "updated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "reason": reason,
                "this_week": len(this_week),
                "last_week": len(last_week),
                "total": len(combined)
            },
            "events": combined
        }, f, indent=2)
    print(f"[SAVE] {len(this_week)}+{len(last_week)}={len(combined)} ({reason})")


def save_state(reason, fetched):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump({"last_run": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "action": reason, "fetched": fetched}, f)


def do_fetch(reason):
    data = fetch_ff()
    if data:
        archive_week(data)
        last = load_last_week()
        cleanup()
        save(data, last, reason)
        save_state(reason, True)
        return True
    save_state(reason + "_failed", False)
    return False


def main():
    print(f"=== EcoNews Live [{now.strftime('%Y-%m-%d %H:%M:%S UTC')}] ===")

    current = load_current_events()
    print(f"[INFO] {len(current)} Events in Datei")

    # Events leer? IMMER fetchen, egal was
    if not current:
        print("[FETCH] Events leer -> hole Daten")
        do_fetch("init")
        return

    # Wochenende? Nur regulaere Updates, keine Actual-Fetches
    if is_weekend():
        if need_regular_fetch():
            do_fetch("weekend_update")
        else:
            print("[SKIP] Wochenende + Daten frisch")
            save_state("skip_weekend", False)
        return

    # Event gerade passiert? Actual holen
    if need_actual_fetch(current):
        do_fetch("actual_fetch")
        return

    # Daten alt?
    if need_regular_fetch():
        do_fetch("regular_update")
        return

    print("[SKIP] Alles frisch")
    save_state("skip_fresh", False)


if __name__ == "__main__":
    main()
