// The agent's window into the record: scripts/search.py --json, unchanged.
// Ranking, query cleaning and spelling variants live in search.py; this file
// only runs it and trims the output to what an answer needs.

import { execFile } from 'node:child_process';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { defineTool } from '@flue/runtime';
import * as v from 'valibot';

// flue run is launched from agent/, so the repo root is one level up.
const ROOT = process.env.COUNCIL_ROOT ?? path.resolve(process.cwd(), '..');
const PYTHON = process.env.COUNCIL_PYTHON ?? path.join(ROOT, '.venv', 'bin', 'python');
const SEARCH = path.join(ROOT, 'scripts', 'search.py');

export function runSearch(args: string[], signal?: AbortSignal): Promise<unknown> {
	return new Promise((resolve, reject) => {
		execFile(
			PYTHON,
			['-W', 'ignore', SEARCH, ...args],
			{ cwd: ROOT, timeout: 20_000, maxBuffer: 16 * 1024 * 1024, signal },
			(err, stdout, stderr) => {
				if (err) {
					const line = (stderr || err.message).trim().split('\n').pop();
					return reject(new Error(`search.py failed: ${line}`));
				}
				try {
					resolve(JSON.parse(stdout));
				} catch {
					reject(new Error(`search.py returned no JSON: ${stdout.trim().split('\n').pop()}`));
				}
			},
		);
	});
}

/**
 * Years the index holds nothing for. Read from the database rather than
 * hardcoded: the gap shrinks as the Clerk's Journals are parsed, and an agent
 * that claims a year is missing after we indexed it is worse than one that
 * says nothing.
 */
export function yearsNotIndexed(): number[] {
	try {
		const db = new DatabaseSync(path.join(ROOT, 'db', 'council_record.db'), {
			readOnly: true,
		});
		try {
			const rows = db
				.prepare('SELECT DISTINCT event_year AS y FROM agenda_items ORDER BY 1')
				.all() as { y: number }[];
			if (!rows.length) return [];
			const have = new Set(rows.map((r) => r.y));
			const missing: number[] = [];
			for (let y = rows[0].y; y <= rows[rows.length - 1].y; y++) {
				if (!have.has(y)) missing.push(y);
			}
			return missing;
		} finally {
			db.close();
		}
	} catch {
		return [];
	}
}

type Result = {
	title: string;
	action: string | null;
	date: string;
	body: string;
	agenda_number: string | null;
	matter_file: string | null;
	url: string;
};

const year = v.optional(v.pipe(v.string(), v.regex(/^\d{4}(-\d{2}-\d{2})?$/)));

export const searchRecord = defineTool({
	name: 'search_record',
	description:
		'Keyword search over Detroit City Council agenda items (May 2013 – Mar 2017 and 2022 – present). ' +
		'Returns the best-matching items, each with date, body, title, outcome and a link to the official record. ' +
		'Use plain keywords that would appear in legislation ("water shut off", "Land Bank", "demolition contract"), not a question. ' +
		'Put an exact phrase in double quotes. Uppercase OR widens a search: water OR sewer.',
	input: v.object({
		query: v.pipe(v.string(), v.minLength(1)),
		since: year,
		until: year,
		body: v.optional(v.string()),
		limit: v.optional(v.pipe(v.number(), v.integer(), v.minValue(1), v.maxValue(20))),
	}),
	async run({ data, signal }) {
		const args = [data.query, '--json', '--limit', String(data.limit ?? 8)];
		if (data.since) args.push('--since', data.since);
		if (data.until) args.push('--until', data.until);
		if (data.body) args.push('--body', data.body);
		const out = (await runSearch(args, signal)) as { count: number; results: Result[] };
		return {
			output: {
				count: out.count,
				results: out.results.map((r, i) => ({
					n: i + 1,
					date: r.date,
					body: r.body,
					item: r.agenda_number,
					file: r.matter_file,
					title: r.title.length > 400 ? r.title.slice(0, 400) + ' …' : r.title,
					outcome: r.action ?? 'none recorded',
					url: r.url,
				})),
			},
		};
	},
});

export const recordTimeline = defineTool({
	name: 'record_timeline',
	description:
		'Count matching agenda items per year for a keyword query, to show how often council returned to a topic. ' +
		'Some years are not in the index at all; the result lists them. A year listed there is a missing record, not zero activity.',
	input: v.object({ query: v.pipe(v.string(), v.minLength(1)) }),
	async run({ data, signal }) {
		const rows = (await runSearch([data.query, '--timeline', '--json'], signal)) as {
			year: number;
			count: number;
		}[];
		return {
			output: {
				total: rows.reduce((a, r) => a + r.count, 0),
				by_year: rows,
				years_not_indexed: yearsNotIndexed(),
			},
		};
	},
});
