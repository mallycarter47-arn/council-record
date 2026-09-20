# About the data

Council Record searches what Detroit City Council actually did. This page
explains where the records come from, what a search result is, what the
tool covers and what it doesn't, and how search works.

Every result links back to the city's own official record, so anything
this tool shows you can be checked at the source.

---

## Where the records come from

Detroit has published its council record in three different systems over
the last decade. No single one covers the whole period.

| Years | Official source | What it contains | In this tool? |
|---|---|---|---|
| May 2013 – Mar 2017 | **Legistar** (`detroit.legistar.com`) | Meetings and agenda items. The city never filled in outcomes here, so these results have no "action taken". | Yes: 457 meetings, 19,547 items |
| 2017 – 2021 | **Journals of Proceedings**, annual PDFs from the City Clerk | The full printed record of each session, including recorded votes | Yes, except 2021: 21,696 items from 2017, 2018, 2019 and 2020 |
| 2022 – present | **eSCRIBE** (`pub-detroitmi.escribemeetings.com`) | Meetings, agenda items, and, where the Clerk has posted minutes, the outcome of each item ("Approved 9-0") | Yes: 1,207 meetings, 48,124 items (Jan 2022 – Sep 2026) |

**In total:** 89,367 agenda items, May 2013 – September 2026, with every year
covered except 2021. About 80% of the 2022-onward items have a recorded
outcome, and the journal years add thousands more, many with the roll-call
vote attached.

**How the data is collected:**
- **Legistar** has a public API. We call it at four requests a second, which
  keeps the load on the city's server light.
- **eSCRIBE** has no public API. We read the same meeting list its public
  calendar page loads, then read each meeting's public agenda or minutes
  page, at the same rate.
- **Everything is saved locally** after it's downloaded. The search runs
  offline from that copy and never contacts the city's servers.

## The gap: April 2017 – 2021, and how much of it is closed

- **Two systems, neither complete.** Legistar stops in March 2017. The last
  full-council meeting in it is January 2015; after that it only has
  committee meetings. eSCRIBE effectively starts in 2022.
- **The record for those years does exist**, as the City Clerk's yearly
  Journals of Proceedings: one PDF per year, each about 2,300–2,800 pages
  ([Journals of City Council](https://detroitmi.gov/government/city-clerk/journals-city-council)).
  They are real text, not scans, and they include the roll-call votes.
- **2017 through 2020 are now searchable** — 21,696 items read straight out
  of those PDFs, with the outcome taken from the clerk's own wording ("Adopted
  as follows: Yeas — … 8"). Each result links to the exact page of the
  official PDF.
- **Only 2021 is still missing.** The Clerk posts that year through Adobe's
  document viewer rather than as a direct PDF, so it hasn't been indexed yet.
- **What you'll see:** the timeline hatches only the years the index truly has
  nothing for, and labels them. A hatched year means the record is missing
  from this tool, not that council did nothing.
- **Journal items read differently** from the other two sources. They are
  printed prose, so titles are the opening words of the item rather than a
  tidy field, and the occasional odd capital letter comes from the PDF's own
  text layer.

## What a search result is

**One result is one agenda item: one thing council was asked to act on.**

- **Examples:** approving a contract, adopting a resolution, receiving a
  report, sending a matter to committee. A full-council formal session
  typically has 150–180 items.
- **What each result shows:**
  - the meeting date
  - which body met: full council (Formal Session) or a named standing committee
  - the item number on that day's agenda (e.g. "8.2")
  - what the item was
  - the outcome, when the minutes record one
  - a link to the official record
- **Why items move between bodies:** most matters go to a committee first
  ("Sent to Formal Session", "Brought Back in 1 week"), then to the full
  council ("Approved 9-0"). So one topic usually leaves a trail of several
  results over weeks or years. The timeline chart shows that trail.
- **Why whole items, not text chunks:** we never cut documents into
  arbitrary snippets. Every result is a real record with a date and a
  source, never a fragment with its context stripped away.

## How search works

- **Keyword search, ranked by relevance.** We use SQLite's built-in
  full-text search with standard BM25 ranking. Words in an item's title
  count more than words elsewhere, and newer items get a small boost.
- **No AI in the search itself.** Results come straight from the record.
  Nothing is generated, summarized or paraphrased. There's an optional
  summary feature that uses Claude; it's off by default, and every sentence
  it writes must cite a specific numbered result.
- **Works offline.** The whole index is one local file, so the tool doesn't
  depend on a network connection.
- **Word endings match.** "demolition" also finds "demolitions";
  "contracting" also finds "contract".

### Spelling: "shutoff" vs. "shut-off"

- **The problem:** the record writes "Water **Shut-offs**". The index splits
  hyphenated words, so it stores "shut" and "off" as two separate words.
- **What went wrong:** someone typing "water shutoff" was searching for a
  single word, "shutoff", that appears nowhere in the index. The search
  returned **0 results** even though council had dealt with the issue
  repeatedly.
- **The fix:** common words that the record writes both as one word and as
  two are now matched in both forms. The list: shutoff, landbank,
  shotspotter, stormwater, streetlight, citywide, cleanup, setback,
  shutdown. "water shutoff", "water shut off" and "water shut-off" now
  return the same results.

## Known limitations

- **2021 is missing** (see "The gap" above). Every other year from 2013 on is covered.
- **No outcomes for 2013–2017.** Legistar has no outcome data, so results
  from those years show no action taken.
- **Not every 2022-onward item has an outcome.** An item shows one only
  when the Clerk has posted minutes that record it. Newer meetings may not
  have minutes yet.
- **Some procedural items remain in the 2013–2017 data**, such as roll call
  and clerk names. They rarely match a real search.
- **Agenda items only.** Meeting video and full legislation text are not
  searched yet.
- **This tool reports the record; it doesn't judge it.** It shows what
  council did and when, not whether it was the right call.

## Reaching council

Search is only half of it. Every page shows the next scheduled meeting, taken
from the city's own calendar, and links to the city's pages for finding your
council member, reading agendas, and speaking at a meeting. Each result also
has an "Email council about this" link that starts a message with the item's
date, body, outcome and official link already filled in.
