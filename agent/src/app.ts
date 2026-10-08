import { Hono } from 'hono';
import { logger } from 'hono/logger';
import { startAlertSchedule } from './alerts.ts';
import { channel as discord } from './channels/discord.ts';

const app = new Hono();

// One line per request, so `fly logs` shows when Discord actually calls us.
// Hono's logger records method, path and status — never the body or token.
app.use('*', logger());

// The route map. Discord posts /ask interactions to
//   https://<public-host>/channels/discord/interactions
// CouncilRecord is reached only through that channel's dispatch; `flue run`
// still runs it directly from the terminal.
app.route('/channels/discord', discord.route());
app.get('/health', (c) => c.text('ok'));

// The daily keyword-alert run (see alerts.ts). Off unless ALERTS_SCHEDULE=1,
// which only the Fly image sets.
startAlertSchedule();

export default app;
