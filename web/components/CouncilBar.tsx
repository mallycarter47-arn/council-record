import type { Meeting } from "@/lib/record";

// Everything here links to the city's own pages rather than restating contact
// details, which go stale. The meeting time is from our own cached copy of
// eSCRIBE's calendar, so it still shows with the network off.
const COUNCIL = "https://detroitmi.gov/government/city-council";
const AGENDAS = "https://detroitmi.gov/government/city-clerk/city-council-agendas-documents";
const CALENDAR = "https://pub-detroitmi.escribemeetings.com/";

function when(iso: string) {
  const d = new Date(iso);
  const day = d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  return `${day}, ${time}`;
}

export default function CouncilBar({ meetings }: { meetings: Meeting[] }) {
  const next = meetings[0];
  return (
    <aside className="cta">
      <div className="cta-head">The record is only half of it — council meets in public</div>
      <div className="cta-rows">
        {next ? (
          <p className="cta-next">
            <span className="cta-label">Next meeting</span>
            <strong>{next.body_name}</strong>
            <span>{when(next.starts_at)}</span>
            {next.location && <span className="cta-loc">{next.location}</span>}
          </p>
        ) : (
          <p className="cta-next">
            <span className="cta-label">Next meeting</span>
            <a href={CALENDAR} target="_blank" rel="noopener noreferrer">
              See the council calendar ↗
            </a>
          </p>
        )}
        <p className="cta-links">
          <a href={COUNCIL} target="_blank" rel="noopener noreferrer">
            Find your council member ↗
          </a>
          <a href={AGENDAS} target="_blank" rel="noopener noreferrer">
            Agendas &amp; how to speak ↗
          </a>
          <a href={CALENDAR} target="_blank" rel="noopener noreferrer">
            Full meeting calendar ↗
          </a>
        </p>
      </div>
    </aside>
  );
}
