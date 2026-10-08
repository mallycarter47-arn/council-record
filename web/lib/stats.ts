// Search counts for the private /stats page. One row per search: the words,
// the filters, how many results came back, and when. No IP, no cookie, nothing
// that identifies the person (see /privacy).
//
// On Fly this lives on the civic_memory_stats volume (STATS_DB=/data/stats.db),
// separate from the read-only council database baked into the image. Logging
// must never break a search, so every write swallows its own errors.

import { mkdirSync } from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

const STATS_DB = process.env.STATS_DB ?? path.resolve(process.cwd(), "..", "data", "stats.db");

let db: DatabaseSync | null = null;

function open(): DatabaseSync {
  if (db) return db;
  mkdirSync(path.dirname(STATS_DB), { recursive: true });
  db = new DatabaseSync(STATS_DB);
  db.exec(`
    PRAGMA journal_mode = WAL;
    CREATE TABLE IF NOT EXISTS searches (
      id       INTEGER PRIMARY KEY,
      at       TEXT NOT NULL,      -- UTC ISO timestamp
      query    TEXT NOT NULL,
      filters  TEXT,               -- JSON of body/since/until/action, if any
      results  INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_searches_at ON searches(at);
  `);
  return db;
}

export function logSearch(query: string, filters: Record<string, string | undefined>, results: number) {
  try {
    const set = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
    open()
      .prepare("INSERT INTO searches (at, query, filters, results) VALUES (?, ?, ?, ?)")
      .run(new Date().toISOString(), query.slice(0, 200), Object.keys(set).length ? JSON.stringify(set) : null, results);
  } catch (e) {
    console.error("[stats] could not log search:", (e as Error).message);
  }
}

export type DayCount = { day: string; searches: number };
export type QueryCount = { query: string; searches: number };

export function statsSummary(days = 30) {
  const d = open();
  const since = new Date(Date.now() - days * 86_400_000).toISOString();
  const one = <T,>(sql: string, ...p: (string | number)[]) => d.prepare(sql).get(...p) as T;
  const all = <T,>(sql: string, ...p: (string | number)[]) => d.prepare(sql).all(...p) as T[];
  return {
    days,
    total: one<{ n: number }>("SELECT COUNT(*) n FROM searches").n,
    recent: one<{ n: number }>("SELECT COUNT(*) n FROM searches WHERE at >= ?", since).n,
    first: one<{ at: string | null }>("SELECT MIN(at) at FROM searches").at,
    perDay: all<DayCount>(
      "SELECT substr(at, 1, 10) day, COUNT(*) searches FROM searches WHERE at >= ? GROUP BY day ORDER BY day DESC",
      since,
    ),
    top: all<QueryCount>(
      "SELECT lower(query) query, COUNT(*) searches FROM searches WHERE at >= ?" +
        " GROUP BY lower(query) ORDER BY searches DESC LIMIT 25",
      since,
    ),
    empty: all<QueryCount>(
      "SELECT lower(query) query, COUNT(*) searches FROM searches WHERE at >= ? AND results = 0" +
        " GROUP BY lower(query) ORDER BY searches DESC LIMIT 25",
      since,
    ),
  };
}
