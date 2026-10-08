// Keyword alerts: the bot's side of scripts/alerts.py. Subscriptions, the
// daily eSCRIBE refresh and the matching all live in Python next to search.py;
// this file runs it, the same way search-record.ts runs search.py.

import { execFile } from 'node:child_process';
import path from 'node:path';

const ROOT = process.env.COUNCIL_ROOT ?? path.resolve(process.cwd(), '..');
const PYTHON = process.env.COUNCIL_PYTHON ?? path.join(ROOT, '.venv', 'bin', 'python');
const ALERTS = path.join(ROOT, 'scripts', 'alerts.py');

// `env` adds variables for this one run — how the Slack install hands over its
// bot token without putting it on the command line.
export function runAlerts(args: string[], timeout = 10_000, env?: Record<string, string>): Promise<any> {
	return new Promise((resolve, reject) => {
		execFile(
			PYTHON,
			['-W', 'ignore', ALERTS, ...args],
			{ cwd: ROOT, timeout, maxBuffer: 16 * 1024 * 1024, env: env ? { ...process.env, ...env } : process.env },
			(err, stdout, stderr) => {
				if (err) {
					const line = (stderr || err.message).trim().split('\n').pop();
					return reject(new Error(`alerts.py failed: ${line}`));
				}
				// The run subcommand prints ingest progress first; the JSON is the last line.
				const last = stdout.trim().split('\n').pop() ?? '';
				try {
					resolve(JSON.parse(last));
				} catch {
					reject(new Error(`alerts.py returned no JSON: ${last}`));
				}
			},
		);
	});
}

// Hourly is enough: alerts.py itself waits until 7am Detroit and runs once a
// day, so a restart or a missed tick never double-posts or skips a day.
const HOUR = 60 * 60 * 1000;

export function startAlertSchedule() {
	if (process.env.ALERTS_SCHEDULE !== '1') return;
	let running = false;
	const tick = async () => {
		if (running) return;
		running = true;
		try {
			const result = await runAlerts(['run'], 15 * 60 * 1000);
			if (!result.skipped) console.log('[alerts]', JSON.stringify(result));
		} catch (err) {
			console.error('[alerts]', (err as Error).message);
		} finally {
			running = false;
		}
	};
	setTimeout(tick, 60_000);
	setInterval(tick, HOUR);
}
