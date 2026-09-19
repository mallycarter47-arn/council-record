#!/usr/bin/env python3
"""
Detroit's record from 2022 on. Legistar (ingest.py) stops in March 2017; the
City Clerk moved to eSCRIBE, which has no public API. This reads the same JSON
the eSCRIBE calendar page uses for the meeting list, then parses each meeting's
HTML page into agenda items.

Where the clerk has posted minutes, the minutes page is used instead of the
agenda: it has the same items plus the outcome ("Approved 9-0"), which goes
into action_name / action_text.

Writes into the same tables as ingest.py, so search.py sees both sources.
eSCRIBE meetings get event_id >= 1,000,000 (mapped in escribe_meetings) so
they never collide with Legistar's integer IDs.

Raw HTML is cached under data/raw/escribe/, so a re-run parses from disk.
Resumable the same way as ingest.py: ctrl-C and re-run.

Usage:
    python scripts/ingest_escribe.py
    python scripts/ingest_escribe.py --since 2024-01-01
    python scripts/ingest_escribe.py --reparse     # after changing the parser
"""

import argparse
import html
import json
import os
import re
import sqlite3
import time
from datetime import date, datetime, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DB_PATH = os.path.join(ROOT, "db", "council_record.db")
SCHEMA_PATH = os.path.join(ROOT, "db", "schema.sql")
RAW_DIR = os.path.join(ROOT, "data", "raw", "escribe")

BASE = "https://pub-detroitmi.escribemeetings.com"
RATE_LIMIT = 0.25
RETRIES = 3
EVENT_ID_BASE = 1_000_000
HEADERS = {"User-Agent": "council-record (civic search project)"}

ITEM_SPLIT = re.compile(r"<DIV class='AgendaItemContainer indent'")
ITEM_NUM = re.compile(r"class='AgendaItem AgendaItem(\d+)'")
COUNTER = re.compile(r"class='AgendaItemCounter'[^>]*>(.*?)</DIV>", re.S)
TITLE = re.compile(r"class='AgendaItemTitle'[^>]*>(.*?)</DIV>", re.S)
DESCR = re.compile(r"class='AgendaItemDescription RichText'[^>]*>(.*?)"
                   r"</DIV></DIV></DIV>", re.S)
MINUTES = re.compile(r"class='AgendaItemMinutes RichText'[^>]*>(.*?)</DIV>", re.S)
# Minutes text leads with the outcome. Formal sessions: "Approved 9-0",
# "Refer to the Public Health and Safety Standing Committee". Committees:
# "MOTION: SEND TO THE FORMAL SESSION AGENDA ...", "CM Waters motion to Bring
# Back in 1 week". First pattern found in the opening words wins, most specific
# first; anything else keeps its full text in action_text only.
ACTIONS = [
    (r"sent? back", "Sent Back"),
    (r"(send|sent|move|moved) to (the )?formal session", "Sent to Formal Session"),
    (r"(move|moved) to new business", "Moved to New Business"),
    (r"(bring|brought) back", "Brought Back"),
    (r"receiv\w* and fil", "Received and Filed"),
    (r"approv", "Approved"), (r"adopt", "Adopted"), (r"refer", "Referred"),
    (r"postpon", "Postponed"), (r"withdr", "Withdrawn"), (r"\bdeni", "Denied"),
    (r"\bfail", "Failed"), (r"\btabl", "Tabled"), (r"reject", "Rejected"),
    (r"\bamend", "Amended"),
]


def text(fragment):
    if not fragment:
        return ""
    s = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def get(session, url, **kw):
    for attempt in range(RETRIES):
        try:
            resp = session.request(kw.pop("method", "GET"), url, timeout=90, **kw)
            if resp.status_code == 200:
                time.sleep(RATE_LIMIT)
                return resp
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = 2 ** attempt
                print(f"    HTTP {resp.status_code}, retrying in {wait}s")
                time.sleep(wait)
                continue
            print(f"  HTTP {resp.status_code} on {url}")
            return None
        except requests.RequestException as exc:
            wait = 2 ** attempt
            print(f"    {type(exc).__name__}, retrying in {wait}s")
            time.sleep(wait)
    return None


def build_db():
    os.makedirs(RAW_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        conn.executescript(fh.read())
    return conn


def fetch_meetings(session, since, until):
    cache = os.path.join(RAW_DIR, "_calendar.json")
    resp = get(session, f"{BASE}/MeetingsCalendarView.aspx/GetCalendarMeetings",
               method="POST",
               json={"calendarStartDate": since, "calendarEndDate": until})
    if resp is not None:
        meetings = resp.json()["d"]
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump(meetings, fh)
    elif os.path.exists(cache):
        print("  Calendar fetch failed; using cached copy.")
        with open(cache, encoding="utf-8") as fh:
            meetings = json.load(fh)
    else:
        return []
    return [m for m in meetings if m.get("HasAgenda") and m["StartDate"][:10] >= since.replace("-", "/")]


def doc_link(meeting, doc_type, fmt):
    for link in meeting.get("MeetingDocumentLink") or []:
        if link.get("Type") == doc_type and link.get("Format") == fmt:
            url = link.get("Url") or ""
            return url if url.startswith("http") else BASE + url
    return None


def event_id_for(conn, guid):
    row = conn.execute("SELECT event_id FROM escribe_meetings WHERE guid = ?",
                       (guid,)).fetchone()
    if row:
        return row[0]
    nxt = conn.execute("SELECT COALESCE(MAX(event_id), ?) + 1 FROM escribe_meetings",
                       (EVENT_ID_BASE - 1,)).fetchone()[0]
    conn.execute("INSERT INTO escribe_meetings (guid, event_id) VALUES (?, ?)",
                 (guid, nxt))
    return nxt


def meeting_page(session, guid, kind):
    """kind is 'PostMinutes' or 'Agenda'. Cached on disk."""
    path = os.path.join(RAW_DIR, f"{guid}.{kind}.html")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    resp = get(session, f"{BASE}/Meeting.aspx",
               params={"Id": guid, "Agenda": kind, "lang": "English"})
    if resp is None:
        return None
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(resp.text)
    return resp.text


def parse_items(page):
    blocks = ITEM_SPLIT.split(page)[1:]
    # Grouped items (e.g. a week of contracts) share one boilerplate title and
    # differ only in the description; for those the description is the title.
    title_counts = {}
    for block in blocks:
        t = text((TITLE.search(block) or [None, ""])[1])
        title_counts[t] = title_counts.get(t, 0) + 1

    items = []
    for seq, block in enumerate(blocks, 1):
        num = ITEM_NUM.search(block)
        title = text((TITLE.search(block) or [None, ""])[1])
        descr = text((DESCR.search(block) or [None, ""])[1])
        minutes = text((MINUTES.search(block) or [None, ""])[1])
        counter = text((COUNTER.search(block) or [None, ""])[1])
        if not title:
            continue
        # Section headers ("UNFINISHED BUSINESS") have no description.
        if not descr and title.upper() == title:
            continue
        if descr and title_counts[title] > 1:
            title = descr if len(descr) <= 200 else descr[:200].rsplit(" ", 1)[0] + " ..."
        opening = minutes[:120].lower()
        action = next((name for pat, name in ACTIONS if re.search(pat, opening)), None)
        items.append({
            "seq": seq,
            "anchor": num.group(1) if num else None,
            "agenda_number": counter or None,
            "title": title,
            "description": descr or None,
            "minutes": minutes or None,
            "action_name": action,
        })
    return items


def load(conn, session, meetings, today):
    done = {r[0] for r in conn.execute(
        "SELECT m.guid FROM escribe_meetings m"
        " JOIN ingest_progress p ON p.event_id = m.event_id")}
    pending = [m for m in meetings
               if m["ID"] not in done and m["StartDate"][:10] <= today]
    pending.sort(key=lambda m: m["StartDate"], reverse=True)

    total = len(pending)
    if not total:
        print("  All meetings already loaded. Nothing to do.")
        return 0, 0
    print(f"  {total} meetings to load, newest first. Safe to ctrl-C.\n")

    n_items = 0
    for n, m in enumerate(pending, 1):
        guid = m["ID"]
        has_minutes = doc_link(m, "PostMinutes", "HTML") is not None
        kind = "PostMinutes" if has_minutes else "Agenda"
        page = meeting_page(session, guid, kind)
        if page is None:
            print(f"  Failed on {m['StartDate']} {m['MeetingName']}. Re-run to resume.")
            break

        event_id = event_id_for(conn, guid)
        edate = m["StartDate"][:10].replace("/", "-")
        body = m.get("MeetingName") or "Unknown body"
        url = f"{BASE}/Meeting.aspx?Id={guid}&Agenda={kind}&lang=English"

        conn.execute(
            "INSERT OR REPLACE INTO events (event_id, body_id, body_name,"
            " event_date, event_year, event_time, location, agenda_file,"
            " minutes_file, insite_url, video_path, minutes_status)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, None, body, edate, int(edate[:4]), m["StartDate"][11:16],
             m.get("Location"), doc_link(m, "Agenda", ".pdf"),
             doc_link(m, "PostMinutes", ".pdf"), url,
             doc_link(m, "Video", "Video"),
             "Final" if has_minutes else None),
        )

        items = parse_items(page)
        conn.execute("DELETE FROM agenda_items WHERE event_id = ?", (event_id,))
        conn.executemany(
            "INSERT INTO agenda_items (item_id, event_id, agenda_number,"
            " sequence, matter_id, matter_file, matter_type, matter_status,"
            " title, action_name, action_text, agenda_note, minutes_note,"
            " passed_flag, event_date, event_year, body_name, insite_url)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(event_id * 1000 + it["seq"], event_id, it["agenda_number"],
              it["seq"], None, None, None, None, it["title"],
              it["action_name"], it["minutes"], it["description"], None, None,
              edate, int(edate[:4]), body,
              url + (f"#AgendaItemAgendaItem{it['anchor']}TitleHeader"
                     if it["anchor"] else ""))
             for it in items],
        )
        conn.execute(
            "INSERT OR REPLACE INTO ingest_progress (event_id, items_loaded, fetched_at)"
            " VALUES (?,?,?)",
            (event_id, len(items), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        n_items += len(items)

        if n % 25 == 0 or n == total:
            print(f"  [{n}/{total}] {edate} {body[:40]:<40} "
                  f"+{len(items):>3} items  (total {n_items:,})")

    return total, n_items


def report(conn):
    print()
    print("=" * 70)
    print("eSCRIBE INGEST SUMMARY")
    print("=" * 70)
    ev = conn.execute(
        "SELECT COUNT(*), MIN(event_date), MAX(event_date) FROM events"
        " WHERE event_id >= ?", (EVENT_ID_BASE,)).fetchone()
    it = conn.execute("SELECT COUNT(*) FROM agenda_items WHERE event_id >= ?",
                      (EVENT_ID_BASE,)).fetchone()[0]
    print(f"  meetings      {ev[0]:,}")
    print(f"  date range    {ev[1]} .. {ev[2]}")
    print(f"  agenda items  {it:,}")
    print()
    print("  items by body (top 12):")
    for body, n in conn.execute(
        "SELECT body_name, COUNT(*) c FROM agenda_items WHERE event_id >= ?"
        " GROUP BY body_name ORDER BY c DESC LIMIT 12", (EVENT_ID_BASE,)
    ):
        print(f"    {n:>7,}  {body}")
    print()
    print("  most common actions:")
    for action, n in conn.execute(
        "SELECT COALESCE(action_name,'(none recorded)'), COUNT(*) c"
        " FROM agenda_items WHERE event_id >= ? GROUP BY 1 ORDER BY c DESC LIMIT 10",
        (EVENT_ID_BASE,)
    ):
        print(f"    {n:>7,}  {action}")
    print()
    total = conn.execute("SELECT COUNT(*), MIN(event_date), MAX(event_date)"
                         " FROM agenda_items").fetchone()
    probe = conn.execute("SELECT COUNT(*) FROM items_fts WHERE items_fts MATCH ?",
                         ("water",)).fetchone()[0]
    print(f"  ALL SOURCES: {total[0]:,} items, {total[1]} .. {total[2]}")
    print(f"  FTS smoke test: 'water' matches {probe:,} items")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2017-01-01")
    ap.add_argument("--reparse", action="store_true",
                    help="re-parse every meeting from cached HTML (after a parser fix)")
    args = ap.parse_args()

    conn = build_db()
    if args.reparse:
        conn.execute("DELETE FROM ingest_progress WHERE event_id >= ?", (EVENT_ID_BASE,))
        conn.commit()
    session = requests.Session()
    session.headers.update(HEADERS)
    today = date.today().isoformat()

    print(f"Loading eSCRIBE meeting list since {args.since}...")
    meetings = fetch_meetings(session, args.since, today)
    print(f"  {len(meetings)} meetings with agendas")
    if not meetings:
        return

    print("\nLoading agenda items...")
    n_events, n_items = load(conn, session, meetings, today.replace("-", "/"))

    conn.execute(
        "INSERT INTO ingest_log (source, events_loaded, items_loaded, earliest,"
        " latest, ingested_at) SELECT ?, ?, ?, MIN(event_date), MAX(event_date), ?"
        " FROM events WHERE event_id >= ?",
        (BASE, n_events, n_items, datetime.now(timezone.utc).isoformat(),
         EVENT_ID_BASE),
    )
    conn.commit()
    report(conn)
    conn.close()


if __name__ == "__main__":
    main()
