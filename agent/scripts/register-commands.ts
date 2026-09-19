// Registers the /ask slash command for this Discord application.
// Run once (re-running is safe; it overwrites the command set):
//   npm run register-commands
import { readFileSync } from 'node:fs';

// Load .env the same way flue run / vite do, without extra dependencies.
for (const line of readFileSync(new URL('../.env', import.meta.url), 'utf8').split('\n')) {
	const m = line.match(/^([A-Z_]+)=(.*)$/);
	if (m && !process.env[m[1]]) process.env[m[1]] = m[2];
}

const appId = process.env.DISCORD_APPLICATION_ID;
const token = process.env.DISCORD_BOT_TOKEN;
if (!appId || !token) throw new Error('Set DISCORD_APPLICATION_ID and DISCORD_BOT_TOKEN in agent/.env');

const commands = [
	{
		name: 'ask',
		type: 1,
		description: 'Ask what Detroit City Council did. Answers cite the official record.',
		options: [
			{
				type: 3,
				name: 'question',
				description: 'e.g. what did council do about water shutoffs?',
				required: true,
				max_length: 300,
			},
		],
		integration_types: [0],
		contexts: [0],
	},
];

const res = await fetch(`https://discord.com/api/v10/applications/${appId}/commands`, {
	method: 'PUT',
	headers: { Authorization: `Bot ${token}`, 'Content-Type': 'application/json' },
	body: JSON.stringify(commands),
});
const body = await res.json();
if (!res.ok) {
	console.error(`Discord said HTTP ${res.status}:`, JSON.stringify(body));
	process.exit(1);
}
console.log(`Registered: ${body.map((c: { name: string }) => '/' + c.name).join(', ')}`);
