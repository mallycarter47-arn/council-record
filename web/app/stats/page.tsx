import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { statsSummary } from "@/lib/stats";

export const metadata: Metadata = { title: "Stats · Civic Memory", robots: { index: false } };
export const dynamic = "force-dynamic";

// Private: only reachable as /stats?key=<STATS_TOKEN>. Without the secret set,
// or with the wrong key, the page doesn't exist.
export default async function Stats(props: PageProps<"/stats">) {
  const { key } = await props.searchParams;
  const token = process.env.STATS_TOKEN;
  if (!token || key !== token) notFound();

  const s = statsSummary(30);
  const max = Math.max(1, ...s.perDay.map((d) => d.searches));

  return (
    <main className="wrap prose">
      <header className="mast">
        <div className="eyebrow">Civic Memory</div>
        <h1>Stats</h1>
        <p>
          {s.recent.toLocaleString()} {s.recent === 1 ? "search" : "searches"} in the last{" "}
          {s.days} days · {s.total.toLocaleString()} all time
          {s.first ? ` (counting since ${s.first.slice(0, 10)})` : ""}
        </p>
      </header>

      <h2>Searches per day</h2>
      {s.perDay.length ? (
        <table className="stats-table">
          <tbody>
            {s.perDay.map((d) => (
              <tr key={d.day}>
                <td>{d.day}</td>
                <td>
                  <span className="stats-bar" style={{ width: `${(d.searches / max) * 100}%` }} />
                </td>
                <td>{d.searches}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p>No searches yet.</p>
      )}

      <h2>Top searches</h2>
      <QueryList rows={s.top} />

      <h2>Searches that found nothing</h2>
      <p>What people looked for and didn&rsquo;t find: spelling variants to add, or gaps in the record.</p>
      <QueryList rows={s.empty} />
    </main>
  );
}

function QueryList({ rows }: { rows: { query: string; searches: number }[] }) {
  if (!rows.length) return <p>None yet.</p>;
  return (
    <ol>
      {rows.map((r) => (
        <li key={r.query}>
          {r.query} <span className="stats-n">× {r.searches}</span>
        </li>
      ))}
    </ol>
  );
}
