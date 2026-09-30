import { parseTimestamp } from "../shared/format";
import type { PhoneMessage } from "./phoneClient";

/** A paged message stream as loaded so far: its messages oldest first, and whether older pages remain. */
export type PhoneMessageStream = { messages: readonly PhoneMessage[]; hasMore: boolean };

/** Which stream the chat page loads an older page of next. */
export type PhoneTimelineSource = "conversation" | "listening";

function messageTime(message: PhoneMessage) {
  return parseTimestamp(message.timestamp)?.getTime() ?? Number.NEGATIVE_INFINITY;
}

/** Up to where a stream's loaded messages are complete: its oldest one while older pages remain, else the beginning. */
function completeSince(stream: PhoneMessageStream) {
  const oldest = stream.messages[0];
  return stream.hasMore && oldest ? messageTime(oldest) : Number.NEGATIVE_INFINITY;
}

/**
 * The group chat page's messages: the conversation and the group's
 * listening records merged by time, each keeping its own order (a tie puts
 * the conversation first). Each stream pages on its own, so only the span
 * both have fully loaded is shown: messages older than the newer of the two
 * streams' oldest loaded messages wait until the other stream's older page
 * arrives. `olderFrom` is the stream bounding that span, whose older page
 * shows more (null when both are complete).
 */
export function phoneChatTimeline(conversation: PhoneMessageStream, listening: PhoneMessageStream) {
  const since = Math.max(completeSince(conversation), completeSince(listening));
  const shown = (stream: PhoneMessageStream) => stream.messages.filter((message) => messageTime(message) >= since);
  const said = shown(conversation);
  const heard = shown(listening);
  const messages: PhoneMessage[] = [];
  let next = 0;
  for (const message of said) {
    const time = messageTime(message);
    for (let early = heard[next]; early && messageTime(early) < time; early = heard[++next]) messages.push(early);
    messages.push(message);
  }
  messages.push(...heard.slice(next));
  const olderFrom: PhoneTimelineSource | null = conversation.hasMore && completeSince(conversation) === since
    ? "conversation"
    : listening.hasMore ? "listening" : null;
  return { messages, hasMore: olderFrom !== null, olderFrom };
}
