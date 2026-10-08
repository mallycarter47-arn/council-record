// flue-blueprint: channel/discord@1
//
// /ask <question> in a Discord server → CouncilRecord searches the record and
// posts a cited answer back into the same channel.
//
// /watch, /unwatch and /watching manage keyword alerts for the channel; the
// daily run that posts them is scripts/alerts.py (scheduled in alerts.ts).
//
// Changes from the blueprint: the acknowledgement is public and echoes the
// question (so the room sees what was asked), answers longer than Discord's
// 2,000-character limit are split, and link previews are suppressed so a
// list of citations doesn't turn into a wall of embeds.

import { REST } from '@discordjs/rest';
import * as v from 'valibot';
import {
	createDiscordChannel,
	type APIInteraction,
	type APIInteractionResponse,
	type DiscordDestinationRef,
} from '@flue/discord';
import { defineTool, dispatch } from '@flue/runtime';
import { CouncilRecord } from '../agents/council-record.ts';
import { runAlerts } from '../alerts.ts';

export const client = new REST({ version: '10' }).setToken(process.env.DISCORD_BOT_TOKEN!);

const SUPPRESS_EMBEDS = 1 << 2;
const EPHEMERAL = 1 << 6;
const MAX_MESSAGE = 1900; // Discord's hard limit is 2,000; leave headroom.
const NO_PINGS = { parse: [] as string[] };

function reply(content: string, ephemeral = false): APIInteractionResponse {
	return {
		type: 4,
		data: {
			content,
			flags: SUPPRESS_EMBEDS | (ephemeral ? EPHEMERAL : 0),
			allowed_mentions: NO_PINGS,
		},
	} as APIInteractionResponse;
}

export const channel = createDiscordChannel({
	publicKey: process.env.DISCORD_PUBLIC_KEY!,

	// Path: /channels/discord/interactions
	async interactions({ interaction }) {
		if (interaction.type !== 2) return reply('Unsupported interaction.', true);
		const name = interaction.data.name;
		if (name === 'watch' || name === 'unwatch' || name === 'watching') {
			return watchCommand(interaction, name);
		}
		if (name !== 'ask') return reply('Unsupported interaction.', true);

		const destination = destinationFromInteraction(interaction);
		if (!destination || destination.type === 'private') {
			return reply('Ask me in a server channel or a DM.', true);
		}

		// The first string option of the `/ask` chat-input command is the question.
		const question =
			interaction.data.type === 1
				? interaction.data.options?.find((option) => option.type === 3)?.value
				: undefined;
		if (typeof question !== 'string' || !question.trim()) {
			return reply('Add a question, like `/ask what did council do about water shutoffs?`', true);
		}

		const channelName = interaction.channel?.name ?? undefined;
		await dispatch(CouncilRecord, {
			id: channel.instanceId(destination),
			// Recorded once when this event creates the instance; ignored after.
			initialData: {
				channelId: destination.channelId,
				...(channelName === undefined ? {} : { channelName }),
			},
			message: {
				kind: 'signal',
				type: 'discord.command.ask',
				body: question,
				attributes: { interactionId: interaction.id, commandName: interaction.data.name },
			},
		});
		return reply(`> ${question.slice(0, 300)}\nSearching the council record…`);
	},
});

function option(interaction: APIInteraction, optionName: string): string | number | undefined {
	if (interaction.type !== 2 || interaction.data.type !== 1) return undefined;
	const found = interaction.data.options?.find((o) => o.name === optionName);
	return found && 'value' in found ? (found.value as string | number) : undefined;
}

async function watchCommand(
	interaction: APIInteraction,
	name: 'watch' | 'unwatch' | 'watching',
): Promise<APIInteractionResponse> {
	const channelId = interaction.channel?.id ?? interaction.channel_id;
	if (!channelId || !interaction.guild_id) return reply('Alerts work in server channels.', true);
	const userId = interaction.member?.user?.id ?? interaction.user?.id;

	try {
		if (name === 'watch') {
			const query = option(interaction, 'search');
			if (typeof query !== 'string' || !query.trim()) {
				return reply('Add what to watch for, like `/watch water shutoff`.', true);
			}
			const args = ['add', '--channel', channelId, '--guild', interaction.guild_id, '--query', query];
			if (userId) args.push('--user', userId);
			const r = await runAlerts(args);
			if (!r.ok) return reply(r.error, true);
			if (r.duplicate) return reply(`This channel already watches **${r.query}** (#${r.id}).`, true);
			const history =
				r.past_matches > 0
					? `It has come up in ${r.past_matches.toLocaleString('en-US')} agenda items since 2013.`
					: 'Nothing in the record matches it yet.';
			return reply(
				`👀 Watching **${r.query}** in this channel (#${r.id}). ${history}\n` +
					'I check new and upcoming agendas every morning and post here when it shows up.',
			);
		}
		if (name === 'unwatch') {
			const id = option(interaction, 'number');
			if (typeof id !== 'number') return reply('Which one? `/watching` lists the numbers.', true);
			const r = await runAlerts(['remove', '--channel', channelId, '--id', String(id)]);
			if (!r.ok) return reply(r.error, true);
			return reply(`Stopped watching **${r.query}** (#${r.id}) in this channel.`);
		}
		const r = await runAlerts(['list', '--channel', channelId]);
		const subs = r.subscriptions as { id: number; query: string }[];
		if (!subs.length) return reply('Nothing watched here yet. Try `/watch water shutoff`.', true);
		return reply(
			'**Watched in this channel**\n' +
				subs.map((s) => `#${s.id} · ${s.query}`).join('\n') +
				'\n`/unwatch <number>` to stop one.',
			true,
		);
	} catch (err) {
		console.error('[watch]', (err as Error).message);
		return reply('Something went wrong saving that. Try again in a minute.', true);
	}
}

// A bare legistar/eSCRIBE URL wraps over two lines in Discord and buries the
// date and outcome that matter. Render each as a short labelled link instead.
function tidyLinks(text: string): string {
	// Unwrap <https://...> first — the model often writes that form, and a bare
	// legistar/eSCRIBE URL still wraps over two lines even with previews off.
	return text
		.replace(/<(https?:\/\/[^>\s]+)>/g, '$1')
		.replace(/(?<![(<[])\bhttps?:\/\/[^\s<>()[\]]+/g, '[official record](<$&>)');
}

// Every /ask answer says who wrote it. Added here rather than in the prompt so
// it can't be left out.
const AI_NOTE = '\n-# AI-written summary of the cited records. Check the links before relying on it.';

function chunks(text: string): string[] {
	const out: string[] = [];
	let rest = tidyLinks(text.trim()) + AI_NOTE;
	while (rest.length > MAX_MESSAGE) {
		let cut = rest.lastIndexOf('\n', MAX_MESSAGE);
		if (cut < MAX_MESSAGE / 2) cut = rest.lastIndexOf(' ', MAX_MESSAGE);
		if (cut < MAX_MESSAGE / 2) cut = MAX_MESSAGE;
		out.push(rest.slice(0, cut).trimEnd());
		rest = rest.slice(cut).trimStart();
	}
	if (rest) out.push(rest);
	return out;
}

export function postMessage(ref: { channelId: string }) {
	return defineTool({
		name: 'post_discord_message',
		description:
			'Post your final answer to the Discord channel this conversation belongs to. ' +
			'Long answers are split into several messages automatically.',
		input: v.object({ content: v.pipe(v.string(), v.minLength(1)) }),
		async run({ data }) {
			const ids: string[] = [];
			for (const part of chunks(data.content)) {
				const result = (await client.post(`/channels/${ref.channelId}/messages`, {
					body: { content: part, flags: SUPPRESS_EMBEDS, allowed_mentions: NO_PINGS },
				})) as { id?: string };
				if (result.id) ids.push(result.id);
			}
			return { output: { messages: ids.length } };
		},
	});
}

function destinationFromInteraction(interaction: APIInteraction): DiscordDestinationRef | undefined {
	const channelId = interaction.channel?.id ?? interaction.channel_id;
	if (!channelId) return undefined;
	if (interaction.guild_id) {
		return { type: 'guild', guildId: interaction.guild_id, channelId };
	}
	if (interaction.context === 2 || interaction.channel?.type === 3) {
		return { type: 'private', channelId };
	}
	if (interaction.context === 1 || interaction.channel?.type === 1) {
		return { type: 'dm', channelId };
	}
	return undefined;
}
