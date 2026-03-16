#!/usr/bin/env python3
"""
EcoNews Live — Smart Calendar Fetcher
======================================
Läuft alle 5 Min via GitHub Actions.
Entscheidet SELBST ob ein ForexFactory-Abruf nötig ist.

Logik:
  1. Wochenende? → SKIP (0 Calls)
  2. Event in letzten 6 Min? → FETCH (Actual holen)
  3. Daten älter als 1 Stunde? → FETCH (reguläres Update)
  4. Sonst → SKIP (nichts tun)

Ergebnis: ~30 echte Fetches/Woche statt 2016 (alle 5 Min blind)
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


# ═══════════════════════════════════════
# ENTSCHEIDUNG: Soll gefetcht werden?
# ═══════════════════════════════════════

def should_skip():
    """Prüft ob wir überhaupt was tun müssen"""
    weekday = now.weekday()  # 0=Mo, 5=Sa, 6=So

    # Wochenende: Keine Actual-Fetches, aber initiale Daten holen erlaubt
    if weekday == 6 and now.hour < 22:
        return "weekend"
    if weekday == 5 and now.hour >= 22:
        return "weekend"

    return False


def need_actual_fetch(events):
    """Prüft ob ein Event in den letzten 6 Minuten stattfand (Actual holen)"""
    cutoff = now - timedelta(minutes=6)
    for evt in events:
        try:
            evt_time = datetime.fromisoformat(evt.get("date", "").replace("Z", "+00:00"))
            if evt_time.tzinfo is None:
                evt_time = evt_time.replace(tzinfo=timezone.utc)

            impact = (evt.get("impact") or "").lower()
            is_important = "high" in impact or "medium" in impact

            if is_important and cutoff <= evt_time <= now:
                actual = evt.get("actual") or ""
                if not actual:
                    print(f"[ACTUAL] Event vor {int((now - evt_time).total_seconds())}s: {evt.get('country','')} {evt.get('title','')}")
                    return True
        except:
            continue
    return False


def need_regular_fetch():
    """Prüft ob die Daten älter als 1 Stunde sind"""
    if not os.path.exists(OUT_FILE):
        print("[FETCH] Keine lokale Datei → erster Abruf")
        return True

    mtime = datetime.fromtimestamp(os.path.getmtime(OUT_FILE), tz=timezone.utc)
    age_min = (now - mtime).total_seconds() / 60

    if age_min > 60:
        print(f"[FETCH] Daten {int(age_min)} Min alt → Update")
        return True

    return False


# ═══════════════════════════════════════
# FETCH + ARCHIV
# ═══════════════════════════════════════

def fetch_forexfactory():
    """Holt aktuelle Woche von ForexFactory"""
    try:
        req = Request(FF_URL, headers={"User-Agent": UA})
        with urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        print(f"[OK] {len(data)} Events geholt")
        return data
    except HTTPError as e:
        if e.code == 429:
            print("[429] Rate Limited → verwende Cache")
        else:
            print(f"[ERR] HTTP {e.code}")
        return None
    except Exception as e:
        print(f"[ERR] {e}")
        return None


def get_week_key(dt=None):
    return (dt or now).strftime("%Y_W%V")


def archive_week(events):
    """Speichert aktuelle Woche als Archiv"""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    key = get_week_key()
    path = os.path.join(ARCHIVE_DIR, f"{key}.json")
    with open(path, "w") as f:
        json.dump(events, f)
    print(f"[ARCHIV] {key}: {len(events)} Events")


def load_last_week():
    """Lädt Vorwoche aus Archiv"""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    key = get_week_key(now - timedelta(weeks=1))
    path = os.path.join(ARCHIVE_DIR, f"{key}.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            data = json.load(f)
        print(f"[ARCHIV] Vorwoche {key}: {len(data)} Events")
        return data
    print(f"[ARCHIV] Keine Vorwoche ({key})")
    return []


def cleanup_archives():
    """Behalte max 4 Wochen"""
    files = sorted(glob.glob(os.path.join(ARCHIVE_DIR, "*.json")))
    for f in files[:-4]:
        os.remove(f)


def load_current_events():
    """Lädt aktuelle Events aus calendar.json"""
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


# ═══════════════════════════════════════
# SPEICHERN
# ═══════════════════════════════════════

def save_combined(this_week, last_week, reason):
    """Speichert letzte + diese Woche als calendar.json"""
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

    print(f"[SAVE] {len(this_week)} diese + {len(last_week)} letzte = {len(combined)} total ({reason})")


def save_state(reason, fetched):
    """Speichert Status für Debugging"""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump({
            "last_run": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "action": reason,
            "fetched": fetched
        }, f, indent=2)


# ═══════════════════════════════════════
# MAIN
# ═══════════════════════════════════════

def main():
    ts = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"═══ EcoNews Live [{ts}] ═══")

    # 1. Wochenende?
    skip = should_skip()

    # 2. Aktuelle Events laden
    current = load_current_events()

    # 3. Wochenende: Keine Actual-Fetches, aber Daten holen wenn leer/alt
    if skip == "weekend":
        if not current or need_regular_fetch():
            print("[WEEKEND] Daten leer/alt → einmaliger Fetch")
            data = fetch_forexfactory()
            if data:
                archive_week(data)
                last = load_last_week()
                cleanup_archives()
                save_combined(data, last, "weekend_init")
                save_state("weekend_init", True)
            else:
                save_state("weekend_fetch_failed", False)
        else:
            print("[SKIP] Wochenende + Daten frisch → nichts tun")
            save_state("skip_weekend", False)
        return

    # 4. Actual-Fetch nötig? (Event in letzten 6 Min)
    if current and need_actual_fetch(current):
        data = fetch_forexfactory()
        if data:
            archive_week(data)
            last = load_last_week()
            cleanup_archives()
            save_combined(data, last, "actual_fetch")
            save_state("actual_fetch", True)
        else:
            save_state("actual_fetch_failed", False)
        return

    # 5. Reguläres Update? (Daten > 1h alt)
    if need_regular_fetch():
        data = fetch_forexfactory()
        if data:
            archive_week(data)
            last = load_last_week()
            cleanup_archives()
            save_combined(data, last, "regular_update")
            save_state("regular_update", True)
        else:
            save_state("regular_update_failed", False)
        return

    # 6. Nichts zu tun
    print("[SKIP] Daten frisch, kein Event gerade → nichts tun")
    save_state("skip_fresh", False)


if __name__ == "__main__":
    main()
