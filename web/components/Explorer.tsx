"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import type { Facets, Result, SearchResponse, YearCount } from "@/lib/record";

const PRESETS = ["water shutoff", "ShotSpotter", "Land Bank"];
const FIRST_YEAR = 2013;
// April 2017 – 2021 is in neither Legistar nor eSCRIBE. See docs/ABOUT_THE_DATA.md.
const GAP = [2018, 2019, 2020, 2021];

type Form = { q: string; body: string; since: string; until: string; action: string };
const EMPTY: Form = { q: "", body: "", since: "", until: "", action: "" };

function stampClass(action: string | null) {
  if (!action) return "none";
  const a = action.toLowerCase();
  if (/approv|adopt|accept/.test(a)) return "approve";
  if (/fail|deni|reject|withdr/.test(a)) return "fail";
  if (/postpon|brought back|tabl|held|sent back/.test(a)) return "hold";
  return "refer";
}

function prettyDate(iso: string) {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export default function Explorer({ facets }: { facets: Facets }) {
  const [form, setForm] = useState<Form>(EMPTY);
  const [ran, setRan] = useState<Form | null>(null);
  const [results, setResults] = useState<Result[] | null>(null);
  const [years, setYears] = useState<YearCount[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const lastYear = new Date().getFullYear();
  const reqId = useRef(0);

  const run = useCallback(async (f: Form, withTimeline = true) => {
    if (!f.q.trim()) return;
    const id = ++reqId.current;
    setLoading(true);
    setError(null);
    const params = new URLSearchParams(
      Object.entries(f).filter(([, v]) => v.trim()) as [string, string][],
    );
    history.replaceState(null, "", "?" + params);
    try {
      const [s, t] = await Promise.all([
        fetch("/api/search?" + params).then((r) => r.json()),
        withTimeline
          ? fetch("/api/timeline?q=" + encodeURIComponent(f.q)).then((r) => r.json())
          : Promise.resolve(null),
      ]);
      if (id !== reqId.current) return;
      if (s.error) throw new Error(s.error);
      setResults((s as SearchResponse).results);
      if (t) setYears(Array.isArray(t) ? t : []);
      setRan(f);
    } catch (e) {
      if (id !== reqId.current) return;
      setError((e as Error).message);
      setResults([]);
    } finally {
      if (id === reqId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const p = new URLSearchParams(location.search);
    const f = { ...EMPTY };
    for (const k of Object.keys(EMPTY) as (keyof Form)[]) f[k] = p.get(k) ?? "";
    setForm(f);
    if (f.q) run(f);
  }, [run]);

  const set = (k: keyof Form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(form, form.q !== ran?.q);
  };

  const pickYear = (y: number) => {
    const on = form.since === String(y) && form.until === String(y);
    const f = { ...form, since: on ? "" : String(y), until: on ? "" : String(y) };
    setForm(f);
    run(f, false);
  };

  const preset = (q: string) => {
    const f = { ...EMPTY, q };
    setForm(f);
    run(f);
  };

  const byYear = new Map(years.map((y) => [y.year, y.count]));
  const total = years.reduce((a, y) => a + y.count, 0);
  const peak = Math.max(1, ...years.map((y) => y.count));
  const span = Array.from({ length: lastYear - FIRST_YEAR + 1 }, (_, i) => FIRST_YEAR + i);
  const pinned = form.since && form.since === form.until ? Number(form.since) : null;
  const filtered = ran && (ran.body || ran.since || ran.until || ran.action);

  return (
    <>
      <form onSubmit={submit} role="search">
        <div className="search">
          <input
            aria-label="Search the record"
            value={form.q}
            onChange={set("q")}
            placeholder="A topic, a street, a neighborhood…"
            autoComplete="off"
            autoFocus
          />
          <button type="submit">Search</button>
        </div>
        <div className="filters">
          <select value={form.body} onChange={set("body")} aria-label="Body">
            <option value="">All bodies</option>
            {facets.bodies.map((b) => (
              <option key={b}>{b}</option>
            ))}
          </select>
          <input value={form.since} onChange={set("since")} placeholder="From year" aria-label="From year" inputMode="numeric" />
          <input value={form.until} onChange={set("until")} placeholder="To year" aria-label="To year" inputMode="numeric" />
          <select value={form.action} onChange={set("action")} aria-label="Outcome">
            <option value="">Any outcome</option>
            {facets.actions.map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
        </div>
      </form>
      <div className="try">
        Try
        {PRESETS.map((p) => (
          <button key={p} type="button" onClick={() => preset(p)}>
            {p}
          </button>
        ))}
      </div>

      {ran && (
        <div className={loading ? "loading" : undefined}>
          <section aria-label="Timeline">
            <div className="head">
              <h2>
                {total.toLocaleString()} item{total === 1 ? "" : "s"} on &ldquo;{ran.q}&rdquo;
              </h2>
              <span className="aside">by year · all bodies · click a year to filter</span>
            </div>
            <div className="chart" style={{ ["--years" as string]: span.length }}>
              {span.map((y) => {
                if (y === GAP[0])
                  return (
                    <div key={y} className="yr gap" style={{ gridColumn: `span ${GAP.length}` }}>
                      <span className="gaplabel">Record not yet indexed<br />Apr 2017 – 2021</span>
                    </div>
                  );
                if (GAP.includes(y)) return null;
                const n = byYear.get(y) ?? 0;
                const cls = ["yr", n === 0 && "zero", pinned && pinned !== y && "dim"].filter(Boolean).join(" ");
                return (
                  <button
                    key={y}
                    type="button"
                    className={cls}
                    aria-pressed={pinned === y}
                    aria-label={`${y}: ${n} items`}
                    title={`${y}: ${n} items`}
                    onClick={() => pickYear(y)}
                  >
                    <span className="n">{n || ""}</span>
                    <span className="b" style={{ height: `${(n / peak) * 82}%` }} />
                  </button>
                );
              })}
            </div>
            <div className="yrs" style={{ ["--years" as string]: span.length }}>
              {span.map((y) => (
                <span key={y}>&rsquo;{String(y).slice(2)}</span>
              ))}
            </div>
            <p className="note">
              The hatched years are missing from this index, not quiet years for council. The
              Clerk&rsquo;s printed Journals cover them.
            </p>
          </section>

          <section aria-label="Results">
            <div className="head">
              <h2>
                {results?.length ? `Top ${results.length}` : "No"} result{results?.length === 1 ? "" : "s"}
                {pinned ? ` in ${pinned}` : ""}
              </h2>
              {filtered && (
                <button type="button" onClick={() => { const f = { ...EMPTY, q: form.q }; setForm(f); run(f, false); }}>
                  Clear filters
                </button>
              )}
            </div>
            {error && <p className="error">Search failed: {error}. Remove any unmatched quote marks and try again.</p>}
            {!error && results?.length === 0 && (
              <p className="empty">
                Nothing in the record matches that. Try fewer words, a different spelling, or an exact phrase in &ldquo;quotes&rdquo;.
              </p>
            )}
            <ol className="results">
              {results?.map((r) => (
                <li key={r.item_id} className="item">
                  <div className="date">
                    {prettyDate(r.date)}
                    {r.agenda_number && <small>Item {r.agenda_number.replace(/\.$/, "")}</small>}
                  </div>
                  <div>
                    <div className="meta">
                      {r.body}
                      {r.matter_file ? ` · File ${r.matter_file}` : ""}
                    </div>
                    <p className="title">{r.title}</p>
                    <div className="foot">
                      <span className={`stamp ${stampClass(r.action)}`}>
                        {r.action ?? "No outcome recorded"}
                      </span>
                      <a href={r.url} target="_blank" rel="noopener noreferrer">
                        Official record ↗
                      </a>
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </div>
      )}
    </>
  );
}
