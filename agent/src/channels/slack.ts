// Civic Memory in Slack: keyword alerts only (no /ask yet).
//
//   /civic watch water shutoff   → post here when it shows up on an agenda
//   /civic list                  → what this channel watches
//   /civic unwatch 3             → stop one
//
// Any workspace can install the app through /slack/install (OAuth). The bot
// token Slack issues is stored by alerts.py, which does the daily posting; this
// file only takes commands, runs the install, and forgets a workspace when it
// uninstalls.
//
// Everything here stays off until the SLACK_* secrets are set on Fly, so the
// Discord bot runs the same with or without Slack configured.

import { randomBytes } from 'node:crypto';
import { Hono } from 'hono';
import { createSlackChannel, type SlackSlashCommandPayload } from '@flue/slack';
import { runAlerts } from '../alerts.ts';

const SIGNING_SECRET = process.env.SLACK_SIGNING_SECRET;
const CLIENT_ID = process.env.SLACK_CLIENT_ID;
const CLIENT_SECRET = process.env.SLACK_CLIENT_SECRET;
const PUBLIC_URL = process.env.PUBLIC_URL ?? 'https://council-record-bot.fly.dev';
const REDIRECT_URI = `${PUBLIC_URL}/slack/oauth`;

// chat:write.public lets alerts post to public channels without inviting the
// app first; private channels still need /invite.
const SCOPES = 'commands,chat:write,chat:write.public';

export const slackEnabled = Boolean(SIGNING_SECRET && CLIENT_ID && CLIENT_SECRET);

const HELP =
	'*Civic Memory alerts*\n' +
	'`/civic watch water shutoff` — post here when it shows up on a council agenda\n' +
	'`/civic list` — what this channel watches\n' +
	'`/civic unwatch 3` — stop one (number from the list)\n' +
	'Search the full record at https://civic-memory.fly.dev';

function say(text: string, inChannel = false) {
	return { response_type: inChannel ? 'in_channel' : 'ephemeral', text };
}

function esc(text: string) {
	return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

async function command(p: SlackSlashCommandPayload) {
	const [verb = '', ...rest] = p.text.trim().split(/\s+/);
	const arg = rest.join(' ');
	try {
		switch (verb.toLowerCase()) {
			case 'watch': {
				if (!arg) return say('Add what to watch for, like `/civic watch water shutoff`.');
				const r = await runAlerts([
					'add', '--platform', 'slack', '--channel', p.channel_id,
					'--guild', p.team_id, '--user', p.user_id, '--query', arg,
				]);
				if (!r.ok) return say(r.error);
				if (r.duplicate) return say(`This channel already watches *${esc(r.query)}* (#${r.id}).`);
				const history =
					r.past_matches > 0
						? `It has come up in ${r.past_matches.toLocaleString('en-US')} agenda items since 2013.`
						: 'Nothing in the record matches it yet.';
				return say(
					`👀 Watching *${esc(r.query)}* in this channel (#${r.id}). ${history}\n` +
						'Civic Memory checks new and upcoming agendas every morning and posts here when it shows up.',
					true,
				);
			}
			case 'unwatch': {
				const id = Number(arg.replace('#', ''));
				if (!Number.isInteger(id) || id < 1) return say('Which one? `/civic list` shows the numbers.');
				const r = await runAlerts(['remove', '--channel', p.channel_id, '--id', String(id)]);
				if (!r.ok) return say(r.error);
				return say(`Stopped watching *${esc(r.query)}* (#${r.id}) in this channel.`, true);
			}
			case 'list':
			case 'watching': {
				const r = await runAlerts(['list', '--channel', p.channel_id]);
				const subs = r.subscriptions as { id: number; query: string }[];
				if (!subs.length) return say('Nothing watched here yet. Try `/civic watch water shutoff`.');
				return say(
					'*Watched in this channel*\n' +
						subs.map((s) => `#${s.id} · ${esc(s.query)}`).join('\n') +
						'\n`/civic unwatch <number>` to stop one.',
				);
			}
			default:
				return say(HELP);
		}
	} catch (err) {
		console.error('[slack]', (err as Error).message);
		return say('Something went wrong saving that. Try again in a minute.');
	}
}

export const channel = createSlackChannel({
	signingSecret: SIGNING_SECRET ?? 'unset',

	// Path: /channels/slack/commands
	async commands({ c, payload }) {
		if (payload.command !== '/civic') return c.json(say('Unknown command.'));
		return c.json(await command(payload));
	},

	// Path: /channels/slack/events — only to forget a workspace that uninstalls.
	async events({ payload }) {
		if (payload.type !== 'event_callback') return;
		const type = payload.event.type;
		if (type === 'app_uninstalled' || type === 'tokens_revoked') {
			await runAlerts(['slack-uninstall', '--team', payload.team_id]).catch((err) =>
				console.error('[slack] uninstall', (err as Error).message),
			);
		}
	},
});

// ---------------------------------------------------------------------------
// "Add to Slack": /slack/install → Slack's consent screen → /slack/oauth
// ---------------------------------------------------------------------------

// One-time state values guard the callback against forged installs. In memory
// is fine: one machine, and an install takes seconds.
const pending = new Map<string, number>();
const STATE_TTL = 10 * 60 * 1000;

function page(title: string, body: string, status = 200) {
	const html = `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title}</title>
<body style="font:17px/1.5 system-ui,sans-serif;max-width:560px;margin:64px auto;padding:0 16px;color:#15202b">
<h1 style="font-size:26px">${title}</h1>${body}</body>`;
	return new Response(html, { status, headers: { 'content-type': 'text/html; charset=utf-8' } });
}

export const oauth = new Hono();

oauth.get('/install', (c) => {
	const now = Date.now();
	for (const [s, t] of pending) if (now - t > STATE_TTL) pending.delete(s);
	const state = randomBytes(16).toString('hex');
	pending.set(state, now);
	const url = new URL('https://slack.com/oauth/v2/authorize');
	url.searchParams.set('client_id', CLIENT_ID!);
	url.searchParams.set('scope', SCOPES);
	url.searchParams.set('redirect_uri', REDIRECT_URI);
	url.searchParams.set('state', state);
	return c.redirect(url.toString());
});

oauth.get('/oauth', async (c) => {
	const { code, state, error } = c.req.query();
	if (error) return page('Not installed', `<p>Slack said: ${esc(error)}. Nothing was installed.</p>`, 400);
	const started = state ? pending.get(state) : undefined;
	if (!code || !started || Date.now() - started > STATE_TTL) {
		return page('Link expired', '<p>Start again from the <a href="/slack/install">install link</a>.</p>', 400);
	}
	pending.delete(state!);

	const res = await fetch('https://slack.com/api/oauth.v2.access', {
		method: 'POST',
		headers: { 'content-type': 'application/x-www-form-urlencoded' },
		body: new URLSearchParams({
			client_id: CLIENT_ID!,
			client_secret: CLIENT_SECRET!,
			code,
			redirect_uri: REDIRECT_URI,
		}),
	});
	const body = (await res.json()) as {
		ok: boolean;
		error?: string;
		access_token?: string;
		bot_user_id?: string;
		team?: { id: string; name?: string };
		authed_user?: { id?: string };
	};
	if (!body.ok || !body.access_token || !body.team?.id) {
		console.error('[slack] oauth', body.error);
		return page('Not installed', '<p>Slack didn\'t complete the install. Try the link again.</p>', 400);
	}

	const args = ['slack-install', '--team', body.team.id];
	if (body.team.name) args.push('--team-name', body.team.name);
	if (body.bot_user_id) args.push('--bot-user', body.bot_user_id);
	if (body.authed_user?.id) args.push('--user', body.authed_user.id);
	await runAlerts(args, 10_000, { SLACK_INSTALL_TOKEN: body.access_token });

	const team = esc(body.team.name ?? 'your workspace');
	return page(
		`Civic Memory is in ${team}`,
		'<p>In any channel, type <code>/civic watch water shutoff</code> (or any topic). ' +
			'Every morning Civic Memory checks new and upcoming Detroit City Council agendas and posts matches there.</p>' +
			'<p>For a private channel, invite it first with <code>/invite @Civic Memory</code>.</p>' +
			'<p><a href="https://civic-memory.fly.dev">Search the full record →</a></p>',
	);
});
