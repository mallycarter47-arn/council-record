#!/usr/bin/env python3
"""
Cache the next few weeks of council meetings from eSCRIBE, so the site can
tell people when they can actually show up — with the network off.

    python scripts/fetch_upcoming.py

COUNCIL_DB overrides the database path. On Fly, the site's and the bot's
daily refreshes run this against their live copies.
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DB_PATH = os.environ.get("COUNCIL_DB") or os.path.join(ROOT, "db", "council_record.db")
SCHEMA_PATH = os.path.join(ROOT, "db", "schema.sql")
BASE = "https://pub-detroitmi.escribemeetings.com"

# eSCRIBE times are Detroit wall-clock times; compare them to Detroit's clock,
# not the server's (UTC on Fly).
now = datetime.now(ZoneInfo("America/Detroit")).replace(tzinfo=None)
today = now.date()
resp = requests.post(
    f"{BASE}/MeetingsCalendarView.aspx/GetCalendarMeetings",
    json={"calendarStartDate": today.isoformat(),
          "calendarEndDate": (today + timedelta(days=60)).isoformat()},
    headers={"User-Agent": "council-record (civic search project)"},
    timeout=60,
)
resp.raise_for_status()
meetings = resp.json()["d"]

conn = sqlite3.connect(DB_PATH)
with open(SCHEMA_PATH, encoding="utf-8") as fh:
    conn.executescript(fh.read())

rows = []
for m in meetings:
    starts = datetime.strptime(m["StartDate"], "%Y/%m/%d %H:%M:%S")
    if starts < now:
        continue
    rows.append((
        m["ID"], m.get("MeetingName") or "Meeting", starts.isoformat(),
        m.get("Location"),
        f"{BASE}/Meeting.aspx?Id={m['ID']}&Agenda=Agenda&lang=English",
        datetime.now(timezone.utc).isoformat(),
    ))

conn.execute("DELETE FROM upcoming_meetings")
conn.executemany(
    "INSERT OR REPLACE INTO upcoming_meetings (guid, body_name, starts_at,"
    " location, url, fetched_at) VALUES (?,?,?,?,?,?)", rows)
conn.commit()

print(f"{len(rows)} upcoming meetings cached")
for guid, body, starts, *_ in rows[:5]:
    print(f"  {starts[:16].replace('T', ' ')}  {body}")
conn.close()
