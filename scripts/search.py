#!/usr/bin/env python3
"""
Step 4. The product. Must give good results from the terminal before any UI.

    python scripts/search.py "water shutoff"
    python scripts/search.py "demolition contract" --body "Formal Session"
    python scripts/search.py "Land Bank" --since 2023 --limit 20
    python scripts/search.py "blight" --json
    python scripts/search.py "water shutoff" --synthesize     # needs ANTHROPIC_API_KEY
    python scripts/search.py --timeline "water shutoff"       # by year, for the demo

Ranking is BM25 from FTS5 with a mild recency nudge. Both parts are visible in
the output so you can explain any result on stage.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "..", "db", "council_record.db")

# Column weights for bm25(). Order matches the fts5 table definition:
# title, action_text, agenda_note, minutes_note, matter_file, body_name
# A hit in the title means far more than a hit in the body name.
BM25_WEIGHTS = (10.0, 3.0, 2.0, 2.0, 5.0, 0.5)

RECENCY_BONUS_PER_YEAR = 0.04   # small. relevance should still win.

FTS_SPECIAL = re.compile(r'[^\w\s"*]')


FTS_OPERATORS = {"AND", "OR", "NOT", "NEAR"}


def clean_query(raw):
    """FTS5 throws on stray punctuation. Strip it, keep quotes for phrases and
    * for prefix matching. Bare multi-word input becomes an AND of terms.

    Operators the user typed themselves (AND / OR / NOT / NEAR, uppercase, as
    FTS5 requires) are passed through instead of being AND-joined — otherwise
    'water OR sewer' becomes 'water AND OR AND sewer' and FTS5 raises a syntax
    error. A trailing or leading operator is dropped rather than crashing."""
    q = FTS_SPECIAL.sub(" ", raw).strip()
    if not q:
        return None
    if '"' in q:
        return q

    tokens = [t for t in q.split() if t]
    parts = []
    for tok in tokens:
        if tok in FTS_OPERATORS:
            # An operator needs a term on both sides.
            if parts and parts[-1] not in FTS_OPERATORS:
                parts.append(tok)
            continue
        if parts and parts[-1] not in FTS_OPERATORS:
            parts.append("AND")
        parts.append(tok)

    while parts and parts[-1] in FTS_OPERATORS:
        parts.pop()
    return " ".join(parts) or None


def search(conn, raw_query, limit=15, body=None, since=None, until=None,
           action=None):
    q = clean_query(raw_query)
    if not q:
        return []

    where = ["items_fts MATCH ?"]
    params = [q]

    if body:
        where.append("ai.body_name LIKE ?")
        params.append(f"%{body}%")
    if since:
        where.append("ai.event_date >= ?")
        params.append(since if len(since) > 4 else f"{since}-01-01")
    if until:
        where.append("ai.event_date <= ?")
        params.append(until if len(until) > 4 else f"{until}-12-31")
    if action:
        where.append("ai.action_name LIKE ?")
        params.append(f"%{action}%")

    sql = f"""
        SELECT
            ai.item_id,
            ai.title,
            ai.matter_file,
            ai.action_name,
            ai.event_date,
            ai.event_year,
            ai.body_name,
            ai.agenda_number,
            ai.insite_url,
            ai.minutes_note,
            bm25(items_fts, {','.join(str(w) for w in BM25_WEIGHTS)}) AS bm,
            snippet(items_fts, 0, '[', ']', ' ... ', 18) AS snip
        FROM items_fts
        JOIN agenda_items ai ON ai.item_id = items_fts.rowid
        WHERE {' AND '.join(where)}
        ORDER BY bm
        LIMIT ?
    """
    params.append(limit * 4)   # over-fetch, then re-rank with recency

    rows = conn.execute(sql, params).fetchall()
    this_year = date.today().year

    results = []
    for r in rows:
        (item_id, title, mfile, action_name, edate, eyear, bname,
         anum, url, minutes, bm, snip) = r
        # bm25 returns negative, more negative = better. Flip for sanity.
        relevance = -bm
        age = max(0, this_year - eyear)
        final = relevance * (1.0 + RECENCY_BONUS_PER_YEAR * max(0, 10 - age))
        results.append({
            "item_id": item_id,
            "title": title,
            "matter_file": mfile,
            "action": action_name,
            "date": edate,
            "year": eyear,
            "body": bname,
            "agenda_number": anum,
            "url": url,
            "minutes_note": (minutes or "")[:400] or None,
            "snippet": snip,
            "relevance": round(relevance, 3),
            "score": round(final, 3),
        })

    results.sort(key=lambda x: -x["score"])
    return results[:limit]


def timeline(conn, raw_query):
    """Count matching items per year. This is the demo money shot: it shows a
    topic council kept returning to, which a ranked list hides."""
    q = clean_query(raw_query)
    if not q:
        return []
    rows = conn.execute(
        "SELECT ai.event_year, COUNT(*) FROM items_fts"
        " JOIN agenda_items ai ON ai.item_id = items_fts.rowid"
        " WHERE items_fts MATCH ?"
        " GROUP BY ai.event_year ORDER BY ai.event_year",
        (q,),
    ).fetchall()
    return [{"year": y, "count": c} for y, c in rows]


def synthesize(query, results):
    """Optional. One Claude call over the top results. Every sentence must cite
    a result number — no citation, no claim. Off by default so the demo never
    depends on the network."""
    try:
        import requests
    except ImportError:
        return "requests not installed"

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return "Set ANTHROPIC_API_KEY to enable synthesis."

    context = "\n\n".join(
        f"[{i+1}] {r['date']} | {r['body']} | {r['matter_file'] or 'no file no.'}\n"
        f"    {r['title']}\n"
        f"    Action: {r['action'] or 'none recorded'}"
        for i, r in enumerate(results)
    )

    prompt = (
        f"These are real agenda items from Detroit City Council, retrieved for "
        f"the query: {query!r}\n\n{context}\n\n"
        "Write 3-5 sentences describing what the record shows. Rules:\n"
        "- Cite every claim with the bracketed number, like [3].\n"
        "- Say only what these items say. If they do not answer the question, "
        "say that plainly.\n"
        "- Do not characterize whether the actions were good, adequate, or "
        "insufficient. Report the record.\n"
        "- Note the date range covered."
    )

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 600,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    if resp.status_code != 200:
        return f"Synthesis failed: HTTP {resp.status_code}"
    return "".join(
        b.get("text", "") for b in resp.json().get("content", [])
        if b.get("type") == "text"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--body", help="filter by body name, substring match")
    ap.add_argument("--since", help="YYYY or YYYY-MM-DD")
    ap.add_argument("--until", help="YYYY or YYYY-MM-DD")
    ap.add_argument("--action", help="filter by action, e.g. Approved")
    ap.add_argument("--timeline", action="store_true", help="counts by year")
    ap.add_argument("--synthesize", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"No database at {DB_PATH}. Run scripts/ingest.py first.")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)

    if args.timeline:
        rows = timeline(conn, args.query)
        if args.json:
            print(json.dumps(rows, indent=2))
            return
        print(f"\n  '{args.query}' — agenda items per year\n")
        peak = max((r["count"] for r in rows), default=1)
        for r in rows:
            bar = "#" * int(40 * r["count"] / peak)
            print(f"    {r['year']}  {bar} {r['count']}")
        print(f"\n  {sum(r['count'] for r in rows)} items total\n")
        return

    results = search(conn, args.query, args.limit, args.body, args.since,
                     args.until, args.action)

    if args.json:
        print(json.dumps({"query": args.query, "count": len(results),
                          "results": results}, indent=2))
        return

    print()
    print("=" * 72)
    print(f"  {args.query}   —   {len(results)} results")
    print("=" * 72)

    if not results:
        print("\n  Nothing matched. Try fewer words, or a phrase in \"quotes\".\n")
        return

    for i, r in enumerate(results, 1):
        print(f"\n  [{i}] {r['date']}  ·  {r['body']}")
        print(f"      {r['title'][:150]}")
        if r["matter_file"]:
            print(f"      file {r['matter_file']}   agenda #{r['agenda_number'] or '-'}")
        if r["action"]:
            print(f"      ACTION: {r['action']}")
        print(f"      {r['url']}")
        print(f"      (relevance {r['relevance']}, ranked {r['score']})")

    print()
    if args.synthesize:
        print("-" * 72)
        print(synthesize(args.query, results))
        print("-" * 72)
        print()


if __name__ == "__main__":
    main()
