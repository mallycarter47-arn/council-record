import CouncilBar from "@/components/CouncilBar";
import Explorer from "@/components/Explorer";
import { facets, nextMeetings } from "@/lib/record";

// Counts come from the local database at request time, so they stay true as
// ingest runs add meetings.
export const dynamic = "force-dynamic";

const year = (iso: string) => iso.slice(0, 4);

export default function Home() {
  const f = facets();
  const meetings = nextMeetings();
  return (
    <main className="wrap">
      <header className="mast">
        <div className="eyebrow">Detroit City Council</div>
        <h1>
          What did council <span>actually do?</span>
        </h1>
        <p>
          The record is public, and split across three city systems that stop and start in
          different years. Search all of them at once: get the agenda item, the date, what
          council did, and a link to the city&rsquo;s own record.
        </p>
        <div className="ledger">
          {f.items.toLocaleString()} agenda items · {f.meetings.toLocaleString()} meetings ·{" "}
          {year(f.first)}–{year(f.last)}
        </div>
      </header>
      <CouncilBar meetings={meetings} />
      <Explorer facets={f} />
      <p className="foot-note">
        Sources: Detroit Legistar (2013–2017), the City Clerk&rsquo;s Journals of Proceedings
        (2017–2020), and eSCRIBE (2022–present) — all read from the city&rsquo;s own public
        records. This tool reports the record; it does not judge it.
      </p>
    </main>
  );
}
