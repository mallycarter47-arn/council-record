# Council Record

Search what Detroit City Council actually did — by topic, by neighborhood, by
council member — and get back the specific agenda item, the date, the action
taken, and a link to the record.

## Why this exists

Detroit's legislative record is technically public and practically unusable.
Both official portals have a search box, and both are real: detroit.legistar.com
searches 2013 to 2018 and stops; pub-detroitmi.escribemeetings.com searches 2022
to now. The four years between are published only as 2,500-page PDFs that
neither one indexes, and 2021 only inside a document viewer you cannot download
from. A resident who wants to know "what has council done about water shutoffs"
has to know all three systems exist, search two of them separately, and skip the
rest.

The information is not hidden, and it is not unfindable one file at a time. What
no official tool does is span the three sources, count what it finds, or rank it
— so the record cannot answer the question people actually have: how often did
council take this up, and what happened each time. The gap is aggregation, not
retrieval.

## Scope

Hackathon build. Demo-only.

**In scope**
- Full-text search across agenda items and legislation, 2015-present
- Every result carries: date, body (council or which committee), the action
  taken, and a deep link to the official record
- Filter by body, by date range, by action outcome
- Optional: a plain-English synthesis over the top N results, with every claim
  citing a specific agenda item

**Out of scope — do not build these**
- User accounts, saved searches, email digests
- Video transcription. It is a rabbit hole and the agenda items are enough for
  a demo. Note it as v2 and move on.
- Any vector database. See "Search approach" below.
- Summarizing what council *should* do. This tool reports the record. The
  moment it editorializes, a judge stops trusting the numbers.

## Stack

- Python 3.11 for ingestion (stdlib + `requests` only)
- SQLite with the **FTS5** extension for search (`db/council_record.db`)
- Next.js (App Router) + TypeScript for the UI
- Optional: Anthropic API for result synthesis, behind a flag, off by default

## Search approach — read this before changing it

**Keyword search with BM25 ranking, via SQLite FTS5. No embeddings.**

This is a deliberate choice, not a shortcut:

- Legislative language is precise and repetitive. People search for the words
  that are actually in the record — "water shutoff", "Land Bank", "demolition
  contract". Keyword search is genuinely strong here.
- Embeddings mean an API call in the retrieval path. If the network is bad in
  the demo room, the product is dead. FTS5 runs off a local file.
- FTS5 gives you snippet highlighting and BM25 ranking for free, with zero
  infrastructure.

If keyword recall proves weak in testing, the fix is query expansion (use Claude
once, at query time, to generate synonyms, then OR them into the FTS query) —
not a vector store.

## Chunking — the thing that makes this good

**One agenda item = one searchable unit.** Not 500-character windows.

This matters more than the ranking algorithm. An agenda item already has
everything a citation needs: meeting date, which body, agenda number, the matter
file number, the title, and the action taken. A result is therefore a real
thing a person can act on, not a text fragment floating free of context.

When you are tempted to chunk minutes PDFs into arbitrary windows: don't. Attach
the minutes note to its agenda item instead.

## Data source

**Legistar Web API** — `https://webapi.legistar.com/v1/detroit`

- No API key required for most clients. If calls 401, Detroit requires a token
  and `explore_source.py` will say so.
- OData query params: `$top`, `$skip`, `$orderby`, `$filter`
- Date filtering uses `datetime'YYYY-MM-DD'` literals

Endpoints used:
- `/bodies` — council and its committees
- `/events` — meetings (date, body, agenda file, minutes file, InSite URL, video path)
- `/events/{id}/eventitems?AgendaNote=1&MinutesNote=1` — the agenda items
- `/matters` — legislation (file number, title, type, status, intro date)

Public web record for deep links: `https://detroit.legistar.com`

## Build order — do not skip ahead

1. `scripts/explore_source.py` — confirm the client slug works, confirm no token
   is needed, print real field names and a sample meeting with its items
2. `db/schema.sql` — adjust if the real fields differ
3. `scripts/ingest.py` — page through events, pull items, build the FTS index.
   **Verify real rows and run a test query before touching any UI.**
4. `scripts/search.py` — must return good results from the terminal first
5. Next.js UI on top. Search box, result list, filters. That is all.

Commit after each step.

## Hard rules

- **Cache everything locally.** `data/raw/` is gitignored. The demo must run
  with the wifi off.
- Rate-limit the ingest. It is someone else's server and you are pulling years
  of meetings. 4 requests/second, and it resumes if interrupted.
- **Every result links to the official record.** If a result cannot produce a
  working legistar.com link, it is a bug, not a minor gap.
- No synthesized claim without a citation to a specific agenda item.
- Show the date on every result. Council action from 2017 and from last month
  look identical in a list and mean completely different things.

## Framing for the demo

Do not pitch it as "AI search for government." Pitch the gap: the record is
public, complete, and unusable. Type a neighborhood name, get everything council
has done about it, ranked, with dates.

Best demo query is one where the answer is surprising and the trail is long —
something the audience assumed council never touched, and the record shows they
touched it nine times.

## Cut order if behind schedule

synthesis -> filters -> matters table -> everything but agenda-item search

The search box survives to the end or there is no project.
