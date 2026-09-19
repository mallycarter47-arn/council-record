#!/usr/bin/env python3
"""
Step 1. Run this FIRST.

Probes the Legistar Web API for Detroit and tells you what is actually there:
whether the client slug works, whether a token is required, the real field
names on events and event items, and what the bodies are called.

Nothing else should be written until this runs clean.

Usage:
    python scripts/explore_source.py
    python scripts/explore_source.py --client detroit
    python scripts/explore_source.py --token YOUR_TOKEN
"""

import argparse
import json
import sys

import requests

BASE = "https://webapi.legistar.com/v1"
DEFAULT_CLIENT = "detroit"


def call(client, path, params=None, token=None, timeout=30):
    params = dict(params or {})
    if token:
        params["token"] = token
    url = f"{BASE}/{client}/{path}"
    resp = requests.get(url, params=params, timeout=timeout,
                        headers={"Accept": "application/json"})
    return resp, url


def check_access(client, token):
    print("=" * 70)
    print(f"ACCESS CHECK  —  client '{client}'")
    print("=" * 70)
    resp, url = call(client, "bodies", {"$top": 1}, token)
    print(f"  GET {url}")
    print(f"  HTTP {resp.status_code}")

    if resp.status_code == 401:
        print("\n  401 — this client requires an API token.")
        print("  Ask the buildathon organizers or the City Clerk's office, then")
        print("  re-run with --token. Do NOT commit the token; use an env var.")
        sys.exit(1)
    if resp.status_code == 404:
        print(f"\n  404 — client slug '{client}' is wrong.")
        print("  The slug is the subdomain of the Legistar site:")
        print("  detroit.legistar.com -> 'detroit'. Try --client with variants.")
        sys.exit(1)
    if resp.status_code != 200:
        print(f"\n  Unexpected status. Body:\n{resp.text[:500]}")
        sys.exit(1)

    print("  OK — no token needed.\n")


def show_bodies(client, token):
    print("=" * 70)
    print("BODIES (council + committees)")
    print("=" * 70)
    resp, _ = call(client, "bodies", {"$top": 200}, token)
    bodies = resp.json()
    print(f"  {len(bodies)} bodies\n")
    for b in bodies:
        active = "" if b.get("BodyActiveFlag", 1) else "  (inactive)"
        print(f"  {b.get('BodyId'):>5}  {b.get('BodyName')}{active}")
    print("\n  Field names on a body:")
    if bodies:
        for k in sorted(bodies[0].keys()):
            print(f"    {k}")
    print()


def show_recent_events(client, token, n=5):
    print("=" * 70)
    print(f"MOST RECENT {n} MEETINGS")
    print("=" * 70)
    resp, url = call(client, "events", {
        "$top": n,
        "$orderby": "EventDate desc",
    }, token)
    print(f"  GET {url}\n")
    events = resp.json()
    if not events:
        print("  No events returned. Something is wrong.")
        sys.exit(1)

    for e in events:
        print(f"  EventId {e.get('EventId')}  {str(e.get('EventDate'))[:10]}  "
              f"{e.get('EventBodyName')}")
        print(f"    agenda:  {e.get('EventAgendaFile') or '-'}")
        print(f"    minutes: {e.get('EventMinutesFile') or '-'}")
        print(f"    insite:  {e.get('EventInSiteURL') or '-'}")
        print(f"    video:   {e.get('EventVideoPath') or '-'}")
        print()

    print("  Field names on an event:")
    for k in sorted(events[0].keys()):
        print(f"    {k}")
    print()
    return events[0]["EventId"]


def show_event_items(client, token, event_id, n=8):
    print("=" * 70)
    print(f"AGENDA ITEMS on EventId {event_id}")
    print("=" * 70)
    resp, url = call(client, f"events/{event_id}/eventitems", {
        "AgendaNote": 1,
        "MinutesNote": 1,
    }, token)
    print(f"  GET {url}\n")

    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code}: {resp.text[:300]}")
        return

    items = resp.json()
    print(f"  {len(items)} items on this agenda\n")

    for it in items[:n]:
        title = (it.get("EventItemTitle") or it.get("EventItemMatterName") or "")[:90]
        print(f"  #{it.get('EventItemAgendaNumber') or '-':<6} "
              f"[{it.get('EventItemMatterFile') or '-'}] {title}")
        if it.get("EventItemActionName"):
            print(f"         action: {it['EventItemActionName']}")
        print()

    if items:
        print("  Field names on an event item:")
        for k in sorted(items[0].keys()):
            print(f"    {k}")
        print()
        print("  FULL FIRST ITEM (copy field names into ingest.py):")
        print(json.dumps(items[0], indent=2)[:2500])
        print()


def show_matters(client, token, n=3):
    print("=" * 70)
    print("MATTERS (legislation) — most recent")
    print("=" * 70)
    resp, url = call(client, "matters", {
        "$top": n,
        "$orderby": "MatterIntroDate desc",
    }, token)
    print(f"  GET {url}\n")
    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code}: {resp.text[:300]}")
        return
    matters = resp.json()
    for m in matters:
        print(f"  {m.get('MatterFile')}  {m.get('MatterTypeName')}  "
              f"{m.get('MatterStatusName')}")
        print(f"    {(m.get('MatterTitle') or '')[:100]}")
        print()
    if matters:
        print("  Field names on a matter:")
        for k in sorted(matters[0].keys()):
            print(f"    {k}")
    print()


def estimate_volume(client, token, since="2015-01-01"):
    print("=" * 70)
    print(f"VOLUME ESTIMATE since {since}")
    print("=" * 70)
    resp, _ = call(client, "events", {
        "$filter": f"EventDate ge datetime'{since}'",
        "$top": 1000,
        "$orderby": "EventDate asc",
    }, token)
    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code}")
        return
    events = resp.json()
    print(f"  {len(events)} meetings in the first page (cap 1000).")
    if len(events) == 1000:
        print("  Hit the page cap — ingest.py must paginate with $skip.")
    if events:
        print(f"  Earliest: {str(events[0].get('EventDate'))[:10]}")
        print(f"  Latest in page: {str(events[-1].get('EventDate'))[:10]}")
    print("\n  Rough item count = meetings x ~40 agenda items each.")
    print("  Budget one API call per meeting for its items, at 4 req/sec.")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", default=DEFAULT_CLIENT)
    ap.add_argument("--token", default=None)
    ap.add_argument("--since", default="2015-01-01")
    args = ap.parse_args()

    check_access(args.client, args.token)
    show_bodies(args.client, args.token)
    event_id = show_recent_events(args.client, args.token)
    show_event_items(args.client, args.token, event_id)
    show_matters(args.client, args.token)
    estimate_volume(args.client, args.token, args.since)

    print("=" * 70)
    print("NEXT: confirm the field names above match db/schema.sql and the")
    print("FIELDS map in scripts/ingest.py, then run ingest.py.")
    print("=" * 70)


if __name__ == "__main__":
    main()
