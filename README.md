# Council Record Index

**Search what Detroit City Council actually did.** Type a topic and get the
agenda items: the date, which body met, what council did, and a link to the
city's own record for every result.

**Live:** [council-record.fly.dev](https://council-record.fly.dev) · also
answers `/ask` in Discord.

---

## The problem

Detroit's legislative record is public, and both official portals have working
search boxes. The trouble is that the record lives in three systems that don't
talk to each other:

| Years | Where the record lives | Searchable there? |
|---|---|---|
| 2013 – 2018 | Legistar (`detroit.legistar.com`) | Yes, then it stops |
| 2017 – 2021 | The City Clerk's annual Journals of Proceedings, 2,300–2,800-page PDFs | No |
| 2022 – now | eSCRIBE (`pub-detroitmi.escribemeetings.com`) | Yes |

So you can find a file. What no official tool does is **span all three, count
what it finds, or rank it** — which is what the question people actually have
requires: *how often has council taken this up, and what happened each time?*

The gap is aggregation, not retrieval.

## What this is

One index over all three sources: **89,367 agenda items across 1,827 meetings,
May 2013 – September 2026**, 48,594 with a recorded outcome and thousands with
the roll-call vote attached. Every year is covered except 2021, which the Clerk
publishes only inside a document viewer that doesn't allow downloads — the
timeline draws that year as a labelled gap rather than a zero, because a
missing record and a quiet year are not the same thing.

Two ways in, one search engine behind both:

- **The site** — search, filters by body, year and outcome, and a timeline of
  how often a topic came back.
- **A Discord bot** — `/ask what did council do about water shutoffs?` returns
  3–4 sentences where every claim carries a numbered citation and a link.

## How it works

```
Legistar API ─┐
eSCRIBE HTML ─┼─→ SQLite + FTS5 ─→ scripts/search.py ──┬─→ web/  (Next.js)
Clerk PDFs  ──┘     (one file)      BM25 ranking       └─→ agent/ (Flue + Discord)
```

Keyword search with BM25 ranking, **no embeddings and no vector database**.
Legislative language is precise and repetitive, so keyword search is genuinely
strong here — and an index that is one local file can't fail because the
network did. `search.py` is the only place ranking, query cleaning and spelling
variants live; the website and the bot both shell out to it.

### The pieces

| Path | What it does |
|---|---|
| `scripts/explore_source.py` | Probes the Legistar API and prints its real field names |
| `scripts/ingest.py` | Legistar (2013–2017) → SQLite |
| `scripts/ingest_escribe.py` | eSCRIBE meetings and minutes (2022–present) |
| `scripts/ingest_journals.py` | The Clerk's PDF journals (2017–2020) → items |
| `scripts/search.py` | The search itself. `--json`, `--timeline`, filters |
| `scripts/fetch_upcoming.py` | Caches upcoming meetings so the site works offline |
| `db/schema.sql` | One row per agenda item, plus the FTS5 index |
| `web/` | Next.js UI |
| `agent/` | Flue agent + Discord channel |

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python scripts/ingest.py --since 2013-01-01     # Legistar
python scripts/ingest_escribe.py                # eSCRIBE
python scripts/ingest_journals.py               # Clerk journals (PDFs in data/raw/journals/)

python scripts/search.py "water shut off"
python scripts/search.py "demolition" --timeline
python scripts/search.py "Land Bank" --since 2023 --json
```

The web UI:

```bash
cd web && npm install && npm run dev        # localhost:3000
```

The Discord bot needs `ANTHROPIC_API_KEY`, `DISCORD_PUBLIC_KEY`,
`DISCORD_BOT_TOKEN` and `DISCORD_APPLICATION_ID` in `agent/.env`:

```bash
cd agent && npm install
npx flue run src/agents/council-record.ts --message "What did council do about water shutoffs?"
```

Both deploy to Fly.io: `fly deploy` for the bot, `fly deploy --config
fly.web.toml` for the site. Each image carries python3 and the database, so
the frozen search path runs unchanged in production.

## Honest limits

- **2021 is missing.** See above; it's the only year.
- **No outcomes before 2018.** Legistar has the meetings but the city never
  filled in what happened, so those results show no action taken.
- **Journal items read like printed prose**, because that is what they are.
  Titles are the opening words of an item, and the occasional odd capital
  letter comes from the PDF's own text layer.
- **Agenda items only.** Meeting video and full legislation text aren't
  indexed yet.
- **It reports the record; it doesn't judge it.** No summarizing of whether
  council did enough, and no claim without a citation.

More detail, written for readers rather than developers:
[`docs/ABOUT_THE_DATA.md`](docs/ABOUT_THE_DATA.md).

## Data sources

- [Legistar Web API](https://webapi.legistar.com/v1/detroit) — Detroit's
  legislative system through 2018
- [eSCRIBE](https://pub-detroitmi.escribemeetings.com/) — meetings and minutes,
  2022 to now
- [Journals of City Council](https://detroitmi.gov/government/city-clerk/journals-city-council)
  — the Clerk's printed proceedings

Built for the 2026 Venture 313 AI Buildathon, against the Rise Higher pillar of
**Open and Accessible Government**.
