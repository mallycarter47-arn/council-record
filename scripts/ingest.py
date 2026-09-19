#!/usr/bin/env python3
"""
Step 3. Run after explore_source.py confirms the field names below.

Pages through Legistar meetings, pulls the agenda items for each, and loads
everything into SQLite with an FTS5 index over the items.

Resumable: if it dies or you ctrl-C, run it again and it picks up where it
stopped. This matters — a full backfill is thousands of API calls.

Usage:
    python scripts/ingest.py                     # since 2015, council + committees
    python scripts/ingest.py --since 2022-01-01  # faster, good enough to demo
    python scripts/ingest.py --events-only       # meetings without items, quick sanity pass
"""

import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DB_PATH = os.path.join(ROOT, "db", "council_record.db")
SCHEMA_PATH = os.path.join(ROOT, "db", "schema.sql")

BASE = "https://webapi.legistar.com/v1"
CLIENT = "detroit"
INSITE = "https://detroit.legistar.com"

PAGE = 1000            # OData max per request
RATE_LIMIT = 0.25      # seconds between calls. Someone else's server.
RETRIES = 3

# ---------------------------------------------------------------------------
# EDIT after explore_source.py if the real field names differ.
# ---------------------------------------------------------------------------

EVENT_FIELDS = {
    "event_id": "EventId",
    "body_id": "EventBodyId",
    "body_name": "EventBodyName",
    "event_date": "EventDate",
    "event_time": "EventTime",
    "location": "EventLocation",
    "agenda_file": "EventAgendaFile",
    "minutes_file": "EventMinutesFile",
    "insite_url": "EventInSiteURL",
    "video_path": "EventVideoPath",
    "minutes_status": "EventMinutesStatusName",
}

ITEM_FIELDS = {
    "item_id": "EventItemId",
    "agenda_number": "EventItemAgendaNumber",
    "sequence": "EventItemAgendaSequence",
    "matter_id": "EventItemMatterId",
    "matter_file": "EventItemMatterFile",
    "matter_type": "EventItemMatterType",
    "matter_status": "EventItemMatterStatus",
    "title": "EventItemTitle",
    "action_name": "EventItemActionName",
    "action_text": "EventItemActionText",
    "agenda_note": "EventItemAgendaNote",
    "minutes_note": "EventItemMinutesNote",
    "passed_flag": "EventItemPassedFlag",
}

# ---------------------------------------------------------------------------


def api(path, params=None, token=None):
    params = dict(params or {})
    if token:
        params["token"] = token
    url = f"{BASE}/{CLIENT}/{path}"

    for attempt in range(RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=60,
                                headers={"Accept": "application/json"})
            if resp.status_code == 200:
                time.sleep(RATE_LIMIT)
                return resp.json()
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = 2 ** attempt
                print(f"    HTTP {resp.status_code}, retrying in {wait}s")
                time.sleep(wait)
                continue
            print(f"  HTTP {resp.status_code} on {url}")
            print(f"  {resp.text[:300]}")
            return None
        except requests.RequestException as exc:
            wait = 2 ** attempt
            print(f"    {type(exc).__name__}, retrying in {wait}s")
            time.sleep(wait)
    return None


def iso_date(raw):
    if not raw:
        return None
    return str(raw)[:10]


def build_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        conn.executescript(fh.read())
    return conn


def load_bodies(conn, token):
    bodies = api("bodies", {"$top": 500}, token)
    if not bodies:
        return 0
    conn.executemany(
        "INSERT OR REPLACE INTO bodies (body_id, name, type_name, active)"
        " VALUES (?,?,?,?)",
        [(b.get("BodyId"), b.get("BodyName"), b.get("BodyTypeName"),
          int(b.get("BodyActiveFlag") or 0)) for b in bodies],
    )
    conn.commit()
    print(f"  {len(bodies)} bodies loaded")
    return len(bodies)


def load_events(conn, since, token):
    """Page through meetings with $skip until a short page comes back."""
    loaded = 0
    skip = 0
    while True:
        batch = api("events", {
            "$filter": f"EventDate ge datetime'{since}'",
            "$orderby": "EventDate asc",
            "$top": PAGE,
            "$skip": skip,
        }, token)
        if batch is None:
            print("  Event fetch failed. Stopping; re-run to resume.")
            break
        if not batch:
            break

        rows = []
        for e in batch:
            date = iso_date(e.get(EVENT_FIELDS["event_date"]))
            if not date:
                continue
            insite = e.get(EVENT_FIELDS["insite_url"]) or (
                f"{INSITE}/MeetingDetail.aspx?ID={e.get('EventId')}"
            )
            rows.append((
                e.get(EVENT_FIELDS["event_id"]),
                e.get(EVENT_FIELDS["body_id"]),
                e.get(EVENT_FIELDS["body_name"]) or "Unknown body",
                date,
                int(date[:4]),
                e.get(EVENT_FIELDS["event_time"]),
                e.get(EVENT_FIELDS["location"]),
                e.get(EVENT_FIELDS["agenda_file"]),
                e.get(EVENT_FIELDS["minutes_file"]),
                insite,
                e.get(EVENT_FIELDS["video_path"]),
                e.get(EVENT_FIELDS["minutes_status"]),
            ))

        conn.executemany(
            "INSERT OR REPLACE INTO events (event_id, body_id, body_name,"
            " event_date, event_year, event_time, location, agenda_file,"
            " minutes_file, insite_url, video_path, minutes_status)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        loaded += len(rows)
        print(f"  {loaded} meetings...")

        if len(batch) < PAGE:
            break
        skip += PAGE

    return loaded


def load_items(conn, token):
    """One call per meeting. The slow part. Skips meetings already done."""
    pending = conn.execute(
        "SELECT e.event_id, e.event_date, e.event_year, e.body_name, e.insite_url"
        "  FROM events e"
        "  LEFT JOIN ingest_progress p ON p.event_id = e.event_id"
        " WHERE p.event_id IS NULL"
        " ORDER BY e.event_date DESC"
    ).fetchall()

    total = len(pending)
    if total == 0:
        print("  All meetings already have items. Nothing to do.")
        return 0

    print(f"  {total} meetings need items. At {RATE_LIMIT}s each, "
          f"about {total * RATE_LIMIT / 60:.0f} min.")
    print("  Safe to ctrl-C — progress is saved per meeting.\n")

    loaded = 0
    for n, (event_id, date, year, body, insite) in enumerate(pending, 1):
        items = api(f"events/{event_id}/eventitems",
                    {"AgendaNote": 1, "MinutesNote": 1}, token)
        if items is None:
            print(f"  Failed on event {event_id}. Re-run to resume.")
            break

        rows = []
        for it in items:
            title = (it.get(ITEM_FIELDS["title"])
                     or it.get("EventItemMatterName")
                     or it.get("EventItemMatterTitle"))
            if not title:
                continue          # procedural filler, not searchable content
            rows.append((
                it.get(ITEM_FIELDS["item_id"]),
                event_id,
                it.get(ITEM_FIELDS["agenda_number"]),
                it.get(ITEM_FIELDS["sequence"]),
                it.get(ITEM_FIELDS["matter_id"]),
                it.get(ITEM_FIELDS["matter_file"]),
                it.get(ITEM_FIELDS["matter_type"]),
                it.get(ITEM_FIELDS["matter_status"]),
                title,
                it.get(ITEM_FIELDS["action_name"]),
                it.get(ITEM_FIELDS["action_text"]),
                it.get(ITEM_FIELDS["agenda_note"]),
                it.get(ITEM_FIELDS["minutes_note"]),
                it.get(ITEM_FIELDS["passed_flag"]),
                date, year, body, insite,
            ))

        if rows:
            conn.executemany(
                "INSERT OR REPLACE INTO agenda_items (item_id, event_id,"
                " agenda_number, sequence, matter_id, matter_file, matter_type,"
                " matter_status, title, action_name, action_text, agenda_note,"
                " minutes_note, passed_flag, event_date, event_year, body_name,"
                " insite_url)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )

        conn.execute(
            "INSERT OR REPLACE INTO ingest_progress (event_id, items_loaded, fetched_at)"
            " VALUES (?,?,?)",
            (event_id, len(rows), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        loaded += len(rows)

        if n % 25 == 0 or n == total:
            print(f"  [{n}/{total}] {date} {body[:40]:<40} "
                  f"+{len(rows):>3} items  (total {loaded:,})")

    return loaded


def report(conn):
    print()
    print("=" * 70)
    print("INGEST SUMMARY")
    print("=" * 70)

    ev = conn.execute("SELECT COUNT(*), MIN(event_date), MAX(event_date) FROM events").fetchone()
    it = conn.execute("SELECT COUNT(*) FROM agenda_items").fetchone()[0]
    print(f"  meetings      {ev[0]:,}")
    print(f"  date range    {ev[1]} .. {ev[2]}")
    print(f"  agenda items  {it:,}")
    print()

    print("  items by body (top 12):")
    for body, n in conn.execute(
        "SELECT body_name, COUNT(*) c FROM agenda_items"
        " GROUP BY body_name ORDER BY c DESC LIMIT 12"
    ):
        print(f"    {n:>7,}  {body}")
    print()

    print("  most common actions:")
    for action, n in conn.execute(
        "SELECT COALESCE(action_name,'(none recorded)'), COUNT(*) c"
        " FROM agenda_items GROUP BY 1 ORDER BY c DESC LIMIT 8"
    ):
        print(f"    {n:>7,}  {action}")
    print()

    if it == 0:
        print("  ZERO ITEMS. Check ITEM_FIELDS against explore_source.py output.")
        return

    # Prove the FTS index actually works before anyone builds a UI on it.
    probe = conn.execute(
        "SELECT COUNT(*) FROM items_fts WHERE items_fts MATCH ?", ("water",)
    ).fetchone()[0]
    print(f"  FTS smoke test: 'water' matches {probe:,} items")
    if probe == 0:
        print("  FTS index is empty or broken. Do not build the UI yet.")
    else:
        print("  Index is live. Move to scripts/search.py")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2015-01-01")
    ap.add_argument("--token", default=os.environ.get("LEGISTAR_TOKEN"))
    ap.add_argument("--events-only", action="store_true")
    args = ap.parse_args()

    conn = build_db()

    print("Loading bodies...")
    load_bodies(conn, args.token)

    print(f"\nLoading meetings since {args.since}...")
    n_events = load_events(conn, args.since, args.token)
    if n_events == 0:
        print("  No meetings loaded. Check the client slug and --since.")
        sys.exit(1)

    if not args.events_only:
        print("\nLoading agenda items...")
        n_items = load_items(conn, args.token)
    else:
        n_items = 0
        print("\nSkipping items (--events-only).")

    conn.execute(
        "INSERT INTO ingest_log (source, events_loaded, items_loaded, earliest,"
        " latest, ingested_at) SELECT ?, ?, ?, MIN(event_date), MAX(event_date), ?"
        " FROM events",
        (f"{BASE}/{CLIENT}", n_events, n_items,
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()

    report(conn)
    conn.close()


if __name__ == "__main__":
    main()
