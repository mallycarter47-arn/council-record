// The UI's only door into the data. Search and timeline shell out to
// scripts/search.py --json, which is the API contract: ranking, query
// cleaning and spelling variants all live there and nowhere else.
// Facets are plain read-only lookups for the filter dropdowns.

import { execFile } from "node:child_process";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

const ROOT = path.resolve(process.cwd(), "..");
const PYTHON = process.env.COUNCIL_PYTHON ?? path.join(ROOT, ".venv", "bin", "python");
const SEARCH = path.join(ROOT, "scripts", "search.py");
const DB = path.join(ROOT, "db", "council_record.db");

export type Result = {
  item_id: number;
  title: string;
  matter_file: string | null;
  action: string | null;
  date: string;
  year: number;
  body: string;
  agenda_number: string | null;
  url: string;
  minutes_note: string | null;
  snippet: string;
  relevance: number;
  score: number;
};

export type SearchResponse = { query: string; count: number; results: Result[] };
export type YearCount = { year: number; count: number };

export type Filters = {
  q: string;
  body?: string;
  since?: string;
  until?: string;
  action?: string;
  limit?: number;
};

function runSearchPy(args: string[]): Promise<unknown> {
  return new Promise((resolve, reject) => {
    execFile(
      /*turbopackIgnore: true*/ PYTHON,
      ["-W", "ignore", SEARCH, ...args],
      { cwd: ROOT, timeout: 20_000, maxBuffer: 16 * 1024 * 1024 },
      (err, stdout, stderr) => {
        if (err) {
          const line = (stderr || err.message).trim().split("\n").pop();
          return reject(new Error(line || "search.py failed"));
        }
        try {
          resolve(JSON.parse(stdout));
        } catch {
          reject(new Error(stdout.trim().split("\n").pop() || "search.py returned no JSON"));
        }
      },
    );
  });
}

export function search(f: Filters): Promise<SearchResponse> {
  const args = [f.q, "--json", "--limit", String(f.limit ?? 25)];
  if (f.body) args.push("--body", f.body);
  if (f.since) args.push("--since", f.since);
  if (f.until) args.push("--until", f.until);
  if (f.action) args.push("--action", f.action);
  return runSearchPy(args) as Promise<SearchResponse>;
}

export function timeline(q: string): Promise<YearCount[]> {
  return runSearchPy([q, "--timeline", "--json"]) as Promise<YearCount[]>;
}

export type Meeting = {
  body_name: string;
  starts_at: string;
  location: string | null;
  url: string | null;
};

// Cached by scripts/fetch_upcoming.py so this works with the network off.
export function nextMeetings(limit = 2): Meeting[] {
  const db = new DatabaseSync(/*turbopackIgnore: true*/ DB, { readOnly: true });
  try {
    return db
      .prepare(
        "SELECT body_name, starts_at, location, url FROM upcoming_meetings" +
          " WHERE starts_at >= ? ORDER BY starts_at LIMIT ?",
      )
      .all(new Date().toISOString().slice(0, 19), limit) as Meeting[];
  } catch {
    return [];
  } finally {
    db.close();
  }
}

export type Facets = {
  bodies: string[];
  actions: string[];
  years: number[];
  items: number;
  meetings: number;
  first: string;
  last: string;
};

export function facets(): Facets {
  const db = new DatabaseSync(/*turbopackIgnore: true*/ DB, { readOnly: true });
  try {
    const col = (sql: string) =>
      (db.prepare(sql).all() as Record<string, string>[]).map((r) => Object.values(r)[0]);
    const totals = db
      .prepare(
        "SELECT (SELECT COUNT(*) FROM agenda_items) AS items," +
          " (SELECT COUNT(*) FROM events) AS meetings," +
          " (SELECT MIN(event_date) FROM agenda_items) AS first," +
          " (SELECT MAX(event_date) FROM agenda_items) AS last",
      )
      .get() as { items: number; meetings: number; first: string; last: string };
    // Which years the index actually covers, so the UI can mark the rest as
    // missing records rather than as quiet years.
    const years = (
      db.prepare("SELECT DISTINCT event_year AS y FROM agenda_items ORDER BY 1").all() as {
        y: number;
      }[]
    ).map((r) => r.y);
    return {
      years,
      bodies: col("SELECT body_name FROM agenda_items GROUP BY 1 ORDER BY COUNT(*) DESC"),
      actions: col(
        "SELECT action_name FROM agenda_items WHERE action_name IS NOT NULL" +
          " GROUP BY 1 ORDER BY COUNT(*) DESC",
      ),
      ...totals,
    };
  } finally {
    db.close();
  }
}
