// flue-blueprint: channel/discord@1
//
// /ask <question> in a Discord server → CouncilRecord searches the record and
// posts a cited answer back into the same channel.
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
		if (interaction.type !== 2 || interaction.data.name !== 'ask') {
			return reply('Unsupported interaction.', true);
		}

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

function chunks(text: string): string[] {
	const out: string[] = [];
	let rest = text.trim();
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
