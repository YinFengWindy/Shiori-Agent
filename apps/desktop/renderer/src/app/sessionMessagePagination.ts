import type {
  SessionMessage,
  SessionMessagePage,
  SessionMessageUpdatePayload,
  SessionPayload,
  SessionSummary,
} from "../shared/types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

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

function messageId(message: SessionMessage): string {
  return String(message.id ?? "").trim();
}

function clientMessageId(message: SessionMessage): string {
  return String(message.metadata?.client_message_id ?? "").trim();
}

function findMatchingMessageIndex(
  messages: readonly SessionMessage[],
  incoming: SessionMessage,
): number {
  const incomingId = messageId(incoming);
  if (incomingId) {
    const idMatch = messages.findIndex((message) => messageId(message) === incomingId);
    if (idMatch >= 0) return idMatch;
  }
  if (typeof incoming.seq === "number") {
    const seqMatch = messages.findIndex((message) => message.seq === incoming.seq);
    if (seqMatch >= 0) return seqMatch;
  }
  const incomingClientMessageId = clientMessageId(incoming);
  if (incomingClientMessageId) {
    return messages.findIndex((message) => clientMessageId(message) === incomingClientMessageId);
  }
  const maxLoadedSeq = messages.reduce(
    (maximum, message) => typeof message.seq === "number" ? Math.max(maximum, message.seq) : maximum,
    -1,
  );
  if (incoming.role === "assistant" && (!incomingId && typeof incoming.seq !== "number"
    || typeof incoming.seq === "number" && incoming.seq > maxLoadedSeq)) {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message?.role === "assistant" && !messageId(message)) return index;
    }
  }
  return -1;
}

function sortSessionMessages(messages: readonly SessionMessage[]): SessionMessage[] {
  const persisted = messages
    .filter((message) => typeof message.seq === "number")
    .sort((left, right) => left.seq! - right.seq!);
  const transient = messages.filter((message) => typeof message.seq !== "number");
  return [...persisted, ...transient];
}

/** Upserts a persisted bridge message while preserving the existing render identity. */
export function mergeSessionMessage(
  messages: readonly SessionMessage[],
  incoming: SessionMessage,
): SessionMessage[] {
  const matchedIndex = findMatchingMessageIndex(messages, incoming);
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

/** Merges one bridge summary/message change without replacing the loaded history page. */
export function mergeSessionSummaryAndMessage(
  current: SessionPayload | null,
  summary: SessionSummary,
  message: SessionMessage | null,
): SessionPayload {
  const messages = current?.key === summary.key ? current.messages : [];
  const matchedMessageIndex = message
    ? findMatchingMessageIndex(messages, message)
    : -1;
  const matchedPersistedMessage = matchedMessageIndex >= 0
    && typeof messages[matchedMessageIndex]?.seq === "number";
  const currentPagination = current?.key === summary.key ? current.pagination : undefined;
  const pagination = currentPagination
    ? {
        ...currentPagination,
        total_count: currentPagination.total_count + (
          message && typeof message.seq === "number" && !matchedPersistedMessage
            ? 1
            : 0
        ),
        newest_seq: message && typeof message.seq === "number"
          ? Math.max(currentPagination.newest_seq ?? message.seq, message.seq)
          : currentPagination.newest_seq,
      }
    : undefined;
  return {
    ...summary,
    messages: message ? mergeSessionMessage(messages, message) : messages,
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

export type { SessionMessageUpdatePayload };
