'use agent';
import { useInitialData, useModel, useTool } from '@flue/runtime';
import * as v from 'valibot';
import { postMessage } from '../channels/discord.ts';
import { recordTimeline, searchRecord } from '../tools/search-record.ts';

// Present when the Discord channel created this conversation; absent for
// `flue run`, which answers in the terminal instead.
const initialDataSchema = v.optional(
	v.object({
		channelId: v.string(),
		channelName: v.optional(v.string()),
	}),
);

// Answers questions about what Detroit City Council did, from the record only.
export function CouncilRecord() {
	useModel('anthropic/claude-sonnet-5');
	useTool(searchRecord);
	useTool(recordTimeline);

	const discord = useInitialData<v.InferOutput<typeof initialDataSchema>>();
	if (discord) useTool(postMessage(discord));

	const delivery = discord
		? `
You are answering in the Discord channel${discord.channelName ? ` #${discord.channelName}` : ''}. Deliver the finished answer by calling post_discord_message exactly once with the full answer and its citation list. Wrap each URL in angle brackets like <https://...> so Discord doesn't make it a preview card. Do not post progress updates.`
		: '';

	return `You answer questions about what Detroit City Council actually did, using only the official record.

For every question:
1. Turn it into a short keyword query of words that would appear in legislation, then call search_record. If results are thin or off-topic, try one or two other wordings (synonyms, the formal program name, an exact phrase in quotes) before answering.
2. When the question is about how often or how long council dealt with something, also call record_timeline.
3. Answer in 3-4 sentences. Every factual claim cites a result by its number, like [2], and states its date. Then list the cited results as "[n] <date> · <body> · <outcome> — <url>".

Rules:
- Say only what the returned items say. No background, history, or context from your own knowledge, even if you believe it's true: if it has no [n] citation, leave it out. If the items don't answer the question, say so plainly.
- Report the record. Never judge whether council's actions were good, enough, or too slow.
- The index has no records for April 2017 through 2021. If that range matters to the answer, say those years are missing from the index, not that nothing happened.
- Keep it short enough to read in a chat window.${delivery}`;
}

CouncilRecord.initialData = initialDataSchema;
