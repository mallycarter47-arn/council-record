import { Hono } from 'hono';
import { channel as discord } from './channels/discord.ts';

const app = new Hono();

// The route map. Discord posts /ask interactions to
//   https://<public-host>/channels/discord/interactions
// CouncilRecord is reached only through that channel's dispatch; `flue run`
// still runs it directly from the terminal.
app.route('/channels/discord', discord.route());
app.get('/health', (c) => c.text('ok'));

export default app;
