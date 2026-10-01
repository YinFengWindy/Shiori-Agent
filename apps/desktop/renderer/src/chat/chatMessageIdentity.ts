import type { SessionMessage, SessionPayload } from "@shiori/sdk";
import { createChatMessageMatcher } from "./chatMessageMatching";

const localChatMessageRenderIdPrefix = "local";
let nextLocalChatMessageRenderId = 0;

function normalizeMessageId(message: SessionMessage): string {
  return String(message.id ?? "").trim();
}

function normalizeRenderId(message: SessionMessage): string {
  return String(message.render_id ?? "").trim();
}

function createLocalChatMessageRenderId(role: string): string {
  nextLocalChatMessageRenderId += 1;
  return `${localChatMessageRenderIdPrefix}:${role}:${nextLocalChatMessageRenderId}`;
}

function createServerChatMessageRenderId(messageId: string): string {
  return `server:${messageId}`;
}

/** Returns the stable React key for one rendered chat message. */
export function getChatMessageReactKey(message: SessionMessage, index: number): string {
  return normalizeRenderId(message)
    || normalizeMessageId(message)
    || `${message.role}-${index}`;
}

/** Returns the DOM lookup key for one rendered chat message. */
export function getChatMessageDomKey(message: SessionMessage, index: number): string {
  return normalizeMessageId(message) || `${message.role}-${index}`;
}

/** Ensures one chat message carries a stable render identity before it is shown in the desktop UI. */
export function ensureChatMessageRenderId(message: SessionMessage): SessionMessage {
  const renderId = normalizeRenderId(message);
  if (renderId) {
    return message;
  }
  const messageId = normalizeMessageId(message);
  return {
    ...message,
    render_id: messageId ? createServerChatMessageRenderId(messageId) : createLocalChatMessageRenderId(message.role),
  };
}

function matchCurrentMessages(current: readonly SessionMessage[], incoming: readonly SessionMessage[]) {
  const matches = new Map<number, number>();
  const claimed = new Set<number>();
  const findMatch = createChatMessageMatcher(current);
  // Explicit identities claim their rows before content fallback can consume them.
  for (const minimumStrength of [4, 3, 2, 1]) {
    incoming.forEach((message, incomingIndex) => {
      if (matches.has(incomingIndex)) return;
      const currentIndex = findMatch(message, claimed, minimumStrength);
      if (currentIndex < 0) return;
      matches.set(incomingIndex, currentIndex);
      claimed.add(currentIndex);
    });
  }
  return matches;
}

/** Reuses compatible identities and allocates unique keys across the complete incoming snapshot. */
export function reconcileSessionMessageRenderIds(
  currentSession: SessionPayload | null,
  incomingSession: SessionPayload | null,
): SessionPayload | null {
  if (!incomingSession) {
    return null;
  }

  const currentMessages = currentSession?.key === incomingSession.key ? currentSession.messages : [];
  const matches = matchCurrentMessages(currentMessages, incomingSession.messages);
  const reserved = new Map<string, number>();
  incomingSession.messages.forEach((message, index) => {
    const key = normalizeRenderId(message);
    if (key && !reserved.has(key)) reserved.set(key, index);
  });
  const used = new Set<string>();
  let changed = false;

  const nextMessages = incomingSession.messages.map((incomingMessage, index) => {
    const currentIndex = matches.get(index);
    const matchedKey = currentIndex == null ? "" : normalizeRenderId(currentMessages[currentIndex]!);
    let key = matchedKey && (!reserved.has(matchedKey) || reserved.get(matchedKey) === index)
      ? matchedKey : normalizeRenderId(incomingMessage);
    if (!key || used.has(key)) {
      const id = normalizeMessageId(incomingMessage);
      key = id ? createServerChatMessageRenderId(id) : "";
      while (!key || used.has(key) || (reserved.has(key) && reserved.get(key) !== index)) {
        key = createLocalChatMessageRenderId(incomingMessage.role);
      }
    }
    used.add(key);
    if (key === normalizeRenderId(incomingMessage)) return incomingMessage;
    changed = true;
    return { ...incomingMessage, render_id: key };
  });

  if (!changed) {
    return incomingSession;
  }
  return {
    ...incomingSession,
    messages: nextMessages,
  };
}
