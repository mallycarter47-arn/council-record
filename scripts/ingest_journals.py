#!/usr/bin/env python3
"""
The missing years. Legistar stops in March 2017 and eSCRIBE starts in 2022;
for everything between, the only public record is the City Clerk's annual
Journal of Proceedings — one ~2,500-page PDF per year of the full council's
sessions, including the roll-call votes.

This reads those PDFs (text layer, no OCR), rebuilds the column-wrapped text
into items, and loads them into the same tables as the other two ingests, so
search.py sees one continuous record.

A journal is a printed book, not a database: items are found by how the clerk
writes them ("11. Council Member ... submitting memorandum relative to ...",
"By Council Member Tate:") and outcomes by the vote lines that follow
("Adopted as follows: Yeas — ... 8."). Expect this source to be rougher than
the other two. Anything that cannot be tied to a session date is skipped.

Usage:
    python scripts/ingest_journals.py                 # every PDF in data/raw/journals
    python scripts/ingest_journals.py --year 2018
    python scripts/ingest_journals.py --year 2018 --pages 200   # quick sample
    python scripts/ingest_journals.py --dry-run       # parse and report, write nothing
"""

import argparse
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone

logging.getLogger("pypdf").setLevel(logging.ERROR)

from pypdf import PdfReader  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DB_PATH = os.path.join(ROOT, "db", "council_record.db")
SCHEMA_PATH = os.path.join(ROOT, "db", "schema.sql")
JOURNAL_DIR = os.path.join(ROOT, "data", "raw", "journals")

EVENT_ID_BASE = 2_000_000
BODY = "City Council (Journal of Proceedings)"

# Where each file lives on the city's site, so every item can deep-link to its
# own page: <url>#page=N opens that page in a browser PDF viewer.
SOURCE_URLS = {
    "2017a": "https://detroitmi.gov/sites/detroitmi.localhost/files/2022-10/2017%20Council_Pt1.pdf",
    "2017b": "https://detroitmi.gov/sites/detroitmi.localhost/files/2022-10/2017%20Council%20Pt2_0.pdf",
    "2017c": "https://detroitmi.gov/sites/detroitmi.localhost/files/2022-10/2017%20Council_Pt3.pdf",
    "2018": "https://detroitmi.gov/sites/detroitmi.localhost/files/2022-10/2018%20Council.pdf",
    "2019": "https://detroitmi.gov/sites/detroitmi.localhost/files/2022-10/2019%20Council.pdf",
    "2020": "https://detroitmi.gov/sites/detroitmi.localhost/files/2022-10/2020%20Council.pdf",
    "2021": "https://detroitmi.gov/government/city-clerk/journals-city-council",
}

MONTHS = ("January February March April May June July August September "
          "October November December").split()
MONTH_NUM = {m: i + 1 for i, m in enumerate(MONTHS)}

# The running head on every page is the session date wrapped around the page
# number: "June 26 1214 2018". Matching that exact shape keeps dates quoted
# inside an item ("dated December 12, 2017") from being read as the session.
DATE_HEAD = re.compile(
    rf"\b({'|'.join(MONTHS)})\s+(\d{{1,2}})\s+\d{{1,5}}\s+(20\d\d)\b")

# Where one item starts: a numbered agenda line, or a member's resolution.
ITEM_START = re.compile(
    r"(?m)^(?:\s*(\d{1,3})\.\s+(?=[A-Z])"
    r"|\s*By (?:Council )?(?:Member|President)[^:\n]{0,60}:)")

VOTE = re.compile(r"Yeas\s*[—–-]\s*(.{0,400}?)\s*[—–-]\s*(\d{1,2})", re.S)
OUTCOMES = [
    (r"adopted as follows", "Adopted"), (r"\badopted\b", "Adopted"),
    (r"\bapproved\b", "Approved"), (r"resolution.{0,40}\bpassed\b", "Adopted"),
    (r"referred to", "Referred"), (r"received and (?:placed on file|filed)", "Received and Filed"),
    (r"\bdenied\b", "Denied"), (r"\bpostponed\b", "Postponed"),
    (r"\bwithdrawn\b", "Withdrawn"), (r"\btabled\b", "Tabled"),
    (r"lost\b", "Failed"),
]
# Text that is procedure, not a council action.
NOISE = re.compile(
    r"^(roll call|present[:\s]|absent|the journal|prayer|pledge|adjourn|"
    r"there being no|approval of the journal|reconsideration|index|"
    r"communications from|miscellaneous|new business|unfinished business|none\.?$)",
    re.I)
SUBSTANCE = re.compile(
    r"relative to|resolution|contract|authoriz|petition|submitting|ordinance|"
    r"request|appropriat|agreement|amend|grant|settlement|acquisition|"
    r"appointment|budget|lease|purchase", re.I)


def dehyphenate(text):
    """The journals are set in narrow columns, so words break across lines
    ("Agree -ment") and sentences wrap mid-phrase. Rebuild the flow."""
    text = re.sub(r"(\w)\s*[-–]\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)
    # Join a line to the next unless it ends a sentence or the next line starts
    # a new item.
    out = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if out and not re.search(r"[.:;!?]$", out[-1]) and not ITEM_START.match(line):
            out[-1] += " " + line
        else:
            out.append(line)
    return "\n".join(out)


def page_date(text, year_hint):
    m = DATE_HEAD.search(text)
    if not m:
        return None
    month, day, year = m.group(1), int(m.group(2)), int(m.group(3))
    # A journal covers one year; anything else on the page is not the session.
    if year_hint and year != year_hint:
        return None
    try:
        return datetime(year, MONTH_NUM[month], day).date().isoformat()
    except ValueError:
        return None


def outcome_of(text):
    low = text.lower()
    for pattern, name in OUTCOMES:
        if re.search(pattern, low):
            return name
    return None


def parse_pdf(path, source_key, year_hint, max_pages=None):
    # A blocked download saves the city's bot-check page under a .pdf name.
    with open(path, "rb") as fh:
        if fh.read(5) != b"%PDF-":
            print(f"  not a PDF (download was blocked?) — skipping {os.path.basename(path)}")
            return [], 0
    reader = PdfReader(path)
    pages = reader.pages if max_pages is None else reader.pages[:max_pages]
    url = SOURCE_URLS.get(source_key, "")
    items, current_date, skipped = [], None, 0

    for page_no, page in enumerate(pages, 1):
        raw = page.extract_text() or ""
        if not raw.strip():
            continue
        current_date = page_date(raw, year_hint) or current_date
        if not current_date:
            continue

        flow = dehyphenate(raw)
        starts = [m.start() for m in ITEM_START.finditer(flow)]
        if not starts:
            continue
        starts.append(len(flow))

        for i in range(len(starts) - 1):
            chunk = flow[starts[i]:starts[i + 1]].strip()
            if len(chunk) < 120 or len(chunk) > 6000:
                skipped += 1
                continue
            if NOISE.match(chunk) or not SUBSTANCE.search(chunk):
                skipped += 1
                continue
            num = re.match(r"\s*(\d{1,3})\.", chunk)
            vote = VOTE.search(chunk)
            items.append({
                "date": current_date,
                "page": page_no,
                "agenda_number": num.group(1) if num else None,
                "title": chunk[:300].rsplit(" ", 1)[0] + (" …" if len(chunk) > 300 else ""),
                "text": chunk,
                "action_name": outcome_of(chunk),
                "vote": f"Yeas {vote.group(2)}" if vote else None,
                "url": f"{url}#page={page_no}",
            })
    return items, skipped


def load(conn, items, source_key):
    by_date = {}
    for it in items:
        by_date.setdefault(it["date"], []).append(it)

    loaded = 0
    for date, rows in sorted(by_date.items()):
        event_id = conn.execute(
            "SELECT event_id FROM journal_sessions WHERE source = ? AND session_date = ?",
            (source_key, date)).fetchone()
        if event_id:
            event_id = event_id[0]
        else:
            event_id = conn.execute(
                "SELECT COALESCE(MAX(event_id), ?) + 1 FROM journal_sessions",
                (EVENT_ID_BASE - 1,)).fetchone()[0]
            conn.execute(
                "INSERT INTO journal_sessions (source, session_date, event_id)"
                " VALUES (?,?,?)", (source_key, date, event_id))

        conn.execute(
            "INSERT OR REPLACE INTO events (event_id, body_id, body_name,"
            " event_date, event_year, event_time, location, agenda_file,"
            " minutes_file, insite_url, video_path, minutes_status)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, None, BODY, date, int(date[:4]), None, None, None,
             SOURCE_URLS.get(source_key), rows[0]["url"], None, "Journal"),
        )
        conn.execute("DELETE FROM agenda_items WHERE event_id = ?", (event_id,))
        conn.executemany(
            "INSERT INTO agenda_items (item_id, event_id, agenda_number,"
            " sequence, matter_id, matter_file, matter_type, matter_status,"
            " title, action_name, action_text, agenda_note, minutes_note,"
            " passed_flag, event_date, event_year, body_name, insite_url)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(event_id * 1000 + n, event_id, r["agenda_number"], n, None, None,
              None, None, r["title"], r["action_name"], r["vote"], r["text"][:4000],
              None, None, r["date"], int(r["date"][:4]), BODY, r["url"])
             for n, r in enumerate(rows, 1)],
        )
        conn.execute(
            "INSERT OR REPLACE INTO ingest_progress (event_id, items_loaded, fetched_at)"
            " VALUES (?,?,?)",
            (event_id, len(rows), datetime.now(timezone.utc).isoformat()))
        loaded += len(rows)
    conn.commit()
    return len(by_date), loaded


def build_db():
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        conn.executescript(fh.read())
    return conn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", help="only this file stem, e.g. 2018 or 2017a")
    ap.add_argument("--pages", type=int, help="parse only the first N pages (testing)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(JOURNAL_DIR) if f.endswith(".pdf"))
    if args.year:
        files = [f for f in files if f.startswith(args.year)]
    if not files:
        print(f"No journal PDFs in {JOURNAL_DIR}. See docs/ABOUT_THE_DATA.md.")
        return

    conn = None if args.dry_run else build_db()
    total_items = 0
    for name in files:
        key = name[:-4]
        year_hint = int(re.match(r"(\d{4})", key).group(1))
        print(f"\n{name}")
        items, skipped = parse_pdf(os.path.join(JOURNAL_DIR, name), key,
                                   year_hint, args.pages)
        dates = sorted({i["date"] for i in items})
        with_outcome = sum(1 for i in items if i["action_name"])
        with_vote = sum(1 for i in items if i["vote"])
        print(f"  {len(items):,} items over {len(dates)} session dates "
              f"({dates[0]} .. {dates[-1]})" if dates else "  no items found")
        print(f"  {with_outcome:,} with an outcome, {with_vote:,} with a recorded vote, "
              f"{skipped:,} fragments skipped")
        if items:
            print(f"  sample: [{items[len(items)//2]['date']}] "
                  f"{items[len(items)//2]['title'][:120]}")
        if conn and items:
            sessions, loaded = load(conn, items, key)
            print(f"  loaded {loaded:,} items across {sessions} sessions")
            total_items += loaded

    if conn:
        conn.execute(
            "INSERT INTO ingest_log (source, events_loaded, items_loaded, earliest,"
            " latest, ingested_at) SELECT ?, COUNT(DISTINCT event_id), ?,"
            " MIN(event_date), MAX(event_date), ? FROM agenda_items WHERE event_id >= ?",
            ("City Clerk Journals of Proceedings", total_items,
             datetime.now(timezone.utc).isoformat(), EVENT_ID_BASE))
        conn.commit()
        rows = conn.execute(
            "SELECT event_year, COUNT(*) FROM agenda_items WHERE event_id >= ?"
            " GROUP BY 1 ORDER BY 1", (EVENT_ID_BASE,)).fetchall()
        print("\nJournal items by year:")
        for year, n in rows:
            print(f"  {year}  {n:,}")
        total = conn.execute("SELECT COUNT(*), MIN(event_date), MAX(event_date)"
                             " FROM agenda_items").fetchone()
        print(f"\nALL SOURCES: {total[0]:,} items, {total[1]} .. {total[2]}")
        conn.close()


if __name__ == "__main__":
    main()
