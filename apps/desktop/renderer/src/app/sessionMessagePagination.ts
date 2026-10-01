import type { SessionMessage, SessionMessagePage, SessionPayload, SessionSummary } from "@shiori/sdk";
import { createChatMessageMatcher } from "../chat/chatMessageMatching";
import { isRecord } from "../shared/isRecord";

function isSessionMessage(value: unknown): value is SessionMessage {
  return isRecord(value) && typeof value.role === "string" && typeof value.content === "string";
}

/** Parses session fields shared by page, mutation, and event bridge responses. */
export function parseSessionSummary(value: unknown): SessionSummary | null {
  if (!isRecord(value)
    || typeof value.key !== "string"
    || typeof value.created_at !== "string"
    || typeof value.updated_at !== "string"
    || typeof value.last_consolidated !== "number"
    || !isRecord(value.metadata)) {
    return null;
  }
  return {
    key: value.key,
    created_at: value.created_at,
    updated_at: value.updated_at,
    last_consolidated: value.last_consolidated,
    metadata: value.metadata,
  };
}

function nullableNumber(value: unknown): number | null {
  return value == null ? null : (typeof value === "number" && Number.isFinite(value) ? value : null);
}

/** Parses one bounded page returned by the desktop session bridge. */
export function parseSessionMessagePage(value: unknown): SessionMessagePage | null {
  if (!isRecord(value) || !Array.isArray(value.messages) || !value.messages.every(isSessionMessage)) {
    return null;
  }
  if (typeof value.limit !== "number" || typeof value.has_more !== "boolean"
    || typeof value.total_count !== "number") {
    return null;
  }
  return {
    messages: value.messages,
    limit: value.limit,
    has_more: value.has_more,
    oldest_seq: nullableNumber(value.oldest_seq),
    newest_seq: nullableNumber(value.newest_seq),
    total_count: value.total_count,
    before_seq: nullableNumber(value.before_seq),
    next_before_seq: nullableNumber(value.next_before_seq),
  };
}

/** Converts the transport page into metadata held alongside renderer-loaded messages. */
export function getSessionPaginationState(page: SessionMessagePage) {
  return {
    limit: page.limit,
    has_more: page.has_more,
    oldest_seq: page.oldest_seq,
    newest_seq: page.newest_seq,
    total_count: page.total_count,
    before_seq: page.before_seq,
    next_before_seq: page.next_before_seq,
  };
}

function sortSessionMessages(messages: readonly SessionMessage[]): SessionMessage[] {
  const persisted = messages
    .filter((message) => typeof message.seq === "number")
    .sort((left, right) => left.seq! - right.seq!);
  const before = new Map<SessionMessage, SessionMessage[]>();
  const tail: SessionMessage[] = [];
  let previousSeq = -1;
  messages.forEach((message, index) => {
    if (message.seq != null) {
      previousSeq = Math.max(previousSeq, message.seq);
      return;
    }
    // Preserve a local row before the following reply, including when that
    // reply arrives before the user's acknowledgement. Older pages cannot anchor it.
    const anchor = messages.slice(index + 1).find((candidate) => (
      candidate.seq != null && candidate.seq > previousSeq
    ));
    if (!anchor) tail.push(message);
    else {
      const group = before.get(anchor) ?? [];
      group.push(message);
      before.set(anchor, group);
    }
  });
  return [...persisted.flatMap((message) => [...(before.get(message) ?? []), message]), ...tail];
}

/** Upserts a persisted bridge message while preserving the existing render identity. */
export function mergeSessionMessage(
  messages: readonly SessionMessage[],
  incoming: SessionMessage,
): SessionMessage[] {
  const matchedIndex = createChatMessageMatcher(messages)(incoming);
  if (matchedIndex >= 0) {
    const current = messages[matchedIndex]!;
    const nextMessages = [...messages];
    nextMessages[matchedIndex] = {
      ...incoming,
      ...(current.render_id ? { render_id: current.render_id } : {}),
    };
    return sortSessionMessages(nextMessages);
  }
  return sortSessionMessages([...messages, incoming]);
}

/** Merges bridge summary/message changes without replacing the loaded history page. */
export function mergeSessionSummaryAndMessage(
  current: SessionPayload | null,
  summary: SessionSummary,
  message: SessionMessage | null,
  additionalMessages: readonly SessionMessage[] = [],
): SessionPayload {
  const messages = current?.key === summary.key ? current.messages : [];
  const incomingMessages = additionalMessages.length > 0
    ? additionalMessages
    : (message ? [message] : []);
  let mergedMessages = messages;
  let appendedPersistedCount = 0;
  let newestSequence = current?.key === summary.key
    ? current.pagination?.newest_seq ?? null
    : null;
  for (const incomingMessage of incomingMessages) {
    const matchedMessageIndex = createChatMessageMatcher(mergedMessages)(incomingMessage);
    const matchedMessage = matchedMessageIndex >= 0 ? mergedMessages[matchedMessageIndex] : null;
    if (typeof incomingMessage.seq === "number"
      && (matchedMessageIndex < 0 || typeof matchedMessage?.seq !== "number")) {
      appendedPersistedCount += 1;
    }
    if (typeof incomingMessage.seq === "number") {
      newestSequence = Math.max(newestSequence ?? incomingMessage.seq, incomingMessage.seq);
    }
    mergedMessages = mergeSessionMessage(mergedMessages, incomingMessage);
  }
  const currentPagination = current?.key === summary.key ? current.pagination : undefined;
  const pagination = currentPagination
    ? {
        ...currentPagination,
        total_count: currentPagination.total_count + appendedPersistedCount,
        newest_seq: newestSequence,
      }
    : undefined;
  return {
    ...summary,
    messages: mergedMessages,
    ...(pagination ? { pagination } : {}),
  };
}

/** Prepends one older page while retaining optimistic and streaming messages already in memory. */
export function mergeSessionMessagePage(
  current: SessionPayload,
  page: SessionMessagePage,
): SessionPayload {
  const messages = page.messages.reduce(
    (accumulator, message) => mergeSessionMessage(accumulator, message),
    current.messages,
  );
  return {
    ...current,
    messages,
    pagination: getSessionPaginationState(page),
  };
}

/** Preserves the loaded history when a refreshed snapshot contains only the newest page. */
export function mergeOpenedSessionSnapshot(
  current: SessionPayload | null,
  incoming: SessionPayload,
): SessionPayload {
  if (!current || current.key !== incoming.key || !incoming.pagination) {
    return incoming;
  }
  const merged = mergeSessionMessagePage(current, {
    ...incoming.pagination,
    messages: incoming.messages,
  });
  return {
    ...incoming,
    messages: merged.messages,
  };
}

export type SessionMessagesAround = {
  sessionKey: string;
  targetMessageId: string;
  messages: SessionMessage[];
};

/** Parses the bounded context returned for a persisted search result. */
export function parseSessionMessagesAround(value: unknown): SessionMessagesAround | null {
  if (!isRecord(value) || typeof value.session_key !== "string"
    || typeof value.target_message_id !== "string" || !Array.isArray(value.messages)
    || !value.messages.every(isSessionMessage)) {
    return null;
  }
  if (!value.messages.some((message) => message.id === value.target_message_id)) {
    return null;
  }
  return {
    sessionKey: value.session_key,
    targetMessageId: value.target_message_id,
    messages: value.messages,
  };
}

/** Merges a search-context slice without changing the sequential older-page cursor. */
export function mergeSessionMessagesAround(
  current: SessionPayload,
  around: SessionMessagesAround,
): SessionPayload {
  const messages = around.messages.reduce(
    (accumulator, message) => mergeSessionMessage(accumulator, message),
    current.messages,
  );
  return { ...current, messages };
}
