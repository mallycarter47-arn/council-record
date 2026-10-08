#!/usr/bin/env python3
"""
Keyword alerts. Someone runs /watch "water shutoff" in a Discord channel; every
morning this re-pulls the meetings around today from eSCRIBE, and when a
watched search matches an item on an upcoming (or just-held) agenda, it posts
the item to that channel. Each item is posted once per subscription.

The bot calls the subcommands and reads their JSON:

    python scripts/alerts.py add --channel C --guild G --user U --query "water shutoff"
    python scripts/alerts.py list --channel C
    python scripts/alerts.py remove --channel C --id 3
    python scripts/alerts.py run              # hourly; acts once a day after 7am Detroit
    python scripts/alerts.py run --force --dry-run --no-refresh   # testing

Matching uses search.py's clean_query, so an alert finds exactly what the same
words find in the search box.
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from search import DB_PATH, clean_query  # noqa: E402

SCHEMA_PATH = os.path.join(HERE, "..", "db", "schema.sql")
DETROIT = ZoneInfo("America/Detroit")
RUN_AFTER_HOUR = 7          # local time; agendas tend to post during the workday
REFRESH_DAYS = 14           # re-pull this far back, for minutes posted late
LOOKBACK_DAYS = 1           # alert on meetings from yesterday onward
MAX_PER_CHANNEL = 25
MAX_ITEMS_PER_ALERT = 10
MAX_MESSAGE = 1900          # Discord's limit is 2,000

# Match the item, not the committee it came up in: body_name is indexed for the
# search box, but there "budget" would alert on every item at the Budget,
# Finance and Audit committee.
ITEM_COLUMNS = "{title action_text agenda_note minutes_note matter_file}"


def connect():
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        conn.executescript(fh.read())
    return conn


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def out(obj):
    print(json.dumps(obj))


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

def item_match(raw_query):
    q = clean_query(raw_query)
    return f"{ITEM_COLUMNS} : ({q})" if q else None


def add(conn, args):
    q = item_match(args.query)
    if not q:
        return out({"ok": False, "error": "That search has no words in it."})
    try:
        total = conn.execute("SELECT COUNT(*) FROM items_fts WHERE items_fts MATCH ?",
                             (q,)).fetchone()[0]
    except sqlite3.OperationalError:
        return out({"ok": False, "error": "I couldn't read that search. Try plain words."})

    query = args.query.strip()
    existing = conn.execute(
        "SELECT id FROM alert_subscriptions WHERE channel_id = ? AND active = 1"
        " AND lower(query) = lower(?)", (args.channel, query)).fetchone()
    if existing:
        return out({"ok": True, "id": existing[0], "query": query, "duplicate": True,
                    "past_matches": total})
    count = conn.execute("SELECT COUNT(*) FROM alert_subscriptions"
                         " WHERE channel_id = ? AND active = 1", (args.channel,)).fetchone()[0]
    if count >= MAX_PER_CHANNEL:
        return out({"ok": False, "error": f"This channel already watches {count} searches. "
                    "Remove one with /unwatch first."})

    cur = conn.execute(
        "INSERT INTO alert_subscriptions (guild_id, channel_id, user_id, query, created_at)"
        " VALUES (?,?,?,?,?)", (args.guild, args.channel, args.user, query, now_iso()))
    conn.commit()
    out({"ok": True, "id": cur.lastrowid, "query": query, "duplicate": False,
         "past_matches": total})


def list_subs(conn, args):
    rows = conn.execute(
        "SELECT id, query, created_at FROM alert_subscriptions"
        " WHERE channel_id = ? AND active = 1 ORDER BY id", (args.channel,)).fetchall()
    out({"ok": True, "subscriptions": [{"id": r[0], "query": r[1], "created_at": r[2]}
                                       for r in rows]})


def remove(conn, args):
    cur = conn.execute("UPDATE alert_subscriptions SET active = 0"
                       " WHERE id = ? AND channel_id = ? AND active = 1",
                       (args.id, args.channel))
    conn.commit()
    if not cur.rowcount:
        return out({"ok": False, "error": f"No watch #{args.id} in this channel. "
                    "Use /watching to see the numbers."})
    row = conn.execute("SELECT query FROM alert_subscriptions WHERE id = ?",
                       (args.id,)).fetchone()
    out({"ok": True, "id": args.id, "query": row[0]})


# ---------------------------------------------------------------------------
# The daily run
# ---------------------------------------------------------------------------

def alert_key(event_id, agenda_number, sequence, title):
    return f"{event_id}:{agenda_number or sequence}:{(title or '')[:80].lower()}"


def matches(conn, sub_id, query, since):
    q = item_match(query)
    if not q:
        return []
    rows = conn.execute(
        """
        SELECT ai.event_id, ai.agenda_number, ai.sequence, ai.title, ai.event_date,
               ai.body_name, ai.insite_url, ai.action_name, e.event_time
        FROM items_fts
        JOIN agenda_items ai ON ai.item_id = items_fts.rowid
        LEFT JOIN events e ON e.event_id = ai.event_id
        WHERE items_fts MATCH ? AND ai.event_date >= ?
        ORDER BY ai.event_date, ai.body_name, ai.sequence
        """, (q, since)).fetchall()
    sent = {r[0] for r in conn.execute(
        "SELECT alert_key FROM alert_sent WHERE subscription_id = ?", (sub_id,))}
    found = []
    for (event_id, anum, seq, title, edate, body, url, action, etime) in rows:
        key = alert_key(event_id, anum, seq, title)
        if key in sent:
            continue
        sent.add(key)
        found.append({"key": key, "agenda_number": anum, "title": title, "date": edate,
                      "time": etime, "body": body, "url": url, "action": action})
    return found


def meeting_label(item):
    d = date.fromisoformat(item["date"])
    label = d.strftime("%a %b ") + str(d.day)
    if item["time"]:
        t = datetime.strptime(item["time"], "%H:%M")
        label += " · " + t.strftime("%I:%M %p").lstrip("0")
    return f"{label} · {item['body']}"


def format_alert(query, items, today):
    lines = [f"🔔 **New on the agenda: `{query}`**"]
    shown = items[:MAX_ITEMS_PER_ALERT]
    last = None
    for it in shown:
        meeting = meeting_label(it)
        if meeting != last:
            when = "upcoming" if it["date"] >= today else "held"
            lines.append(f"\n**{meeting}** ({when})")
            last = meeting
        title = it["title"] if len(it["title"]) <= 180 else it["title"][:180].rsplit(" ", 1)[0] + " …"
        num = f"{it['agenda_number']} " if it["agenda_number"] else ""
        outcome = f" — *{it['action']}*" if it["action"] else ""
        link = f" [official record](<{it['url']}>)" if it["url"] else ""
        lines.append(f"• {num}{title}{outcome}{link}")
    if len(items) > len(shown):
        lines.append(f"\n…and {len(items) - len(shown)} more. "
                     f"Search it: <https://civic-memory.fly.dev/?q={query.replace(' ', '+')}>")
    lines.append("\n-# /unwatch to stop · Civic Memory reports the record; check the link for details.")
    return split("\n".join(lines))


def split(text):
    parts = []
    while len(text) > MAX_MESSAGE:
        cut = text.rfind("\n", 0, MAX_MESSAGE)
        if cut < MAX_MESSAGE // 2:
            cut = MAX_MESSAGE
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        parts.append(text)
    return parts


def post(channel_id, content):
    import requests
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN is not set")
    resp = requests.post(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        headers={"Authorization": f"Bot {token}"},
        json={"content": content, "flags": 1 << 2, "allowed_mentions": {"parse": []}},
        timeout=30,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Discord HTTP {resp.status_code}: {resp.text[:200]}")


def refresh():
    subprocess.run([sys.executable, os.path.join(HERE, "ingest_escribe.py"),
                    "--refresh", str(REFRESH_DAYS), "--quiet"], check=True)


def run(conn, args):
    local = datetime.now(DETROIT)
    run_date = local.date().isoformat()
    if not args.force:
        if local.hour < RUN_AFTER_HOUR:
            return out({"ok": True, "skipped": f"before {RUN_AFTER_HOUR}am Detroit"})
        if conn.execute("SELECT 1 FROM alert_runs WHERE run_date = ? AND finished_at IS NOT NULL",
                        (run_date,)).fetchone():
            return out({"ok": True, "skipped": "already ran today"})

    subs = conn.execute("SELECT id, channel_id, query FROM alert_subscriptions"
                        " WHERE active = 1 ORDER BY id").fetchall()
    if not args.dry_run:
        conn.execute("INSERT OR REPLACE INTO alert_runs (run_date, started_at) VALUES (?, ?)",
                     (run_date, now_iso()))
        conn.commit()

    if not args.no_refresh:
        conn.close()
        refresh()
        conn = connect()

    since = (local.date() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    sent, failed = 0, []
    for sub_id, channel_id, query in subs:
        items = matches(conn, sub_id, query, since)
        if not items:
            continue
        messages = format_alert(query, items, run_date)
        if args.dry_run:
            print(f"--- #{sub_id} -> channel {channel_id}")
            print("\n\n".join(messages))
            continue
        try:
            for m in messages:
                post(channel_id, m)
        except Exception as exc:  # noqa: BLE001 — one bad channel can't stop the rest
            failed.append({"id": sub_id, "error": str(exc)})
            continue
        conn.executemany("INSERT OR IGNORE INTO alert_sent (subscription_id, alert_key, sent_at)"
                         " VALUES (?,?,?)", [(sub_id, it["key"], now_iso()) for it in items])
        conn.commit()
        sent += len(items)

    if not args.dry_run:
        conn.execute("UPDATE alert_runs SET finished_at = ?, alerts_sent = ? WHERE run_date = ?",
                     (now_iso(), sent, run_date))
        conn.commit()
    out({"ok": True, "subscriptions": len(subs), "items_sent": sent, "failed": failed})


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--channel", required=True)
    a.add_argument("--guild")
    a.add_argument("--user")
    a.add_argument("--query", required=True)
    l = sub.add_parser("list")
    l.add_argument("--channel", required=True)
    r = sub.add_parser("remove")
    r.add_argument("--channel", required=True)
    r.add_argument("--id", type=int, required=True)
    n = sub.add_parser("run")
    n.add_argument("--force", action="store_true", help="ignore the time and once-a-day checks")
    n.add_argument("--dry-run", action="store_true", help="print alerts, send and record nothing")
    n.add_argument("--no-refresh", action="store_true", help="skip the eSCRIBE re-pull")
    args = ap.parse_args()

    conn = connect()
    {"add": add, "list": list_subs, "remove": remove, "run": run}[args.cmd](conn, args)


if __name__ == "__main__":
    main()
