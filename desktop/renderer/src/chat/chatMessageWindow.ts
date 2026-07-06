import { getChatMessageDomKey } from "./chatMessageIdentity";
import type { SessionPayload } from "../shared/types";

export const hotChatSessionMessageCount = 160;
export const hotChatSessionMessageCountStep = 120;
const highlightedChatMessageTrailingContext = 24;

function getHotChatSessionStartIndex(totalMessageCount: number, visibleMessageCount: number): number {
  if (totalMessageCount <= 0) {
    return 0;
  }
  return Math.max(0, totalMessageCount - Math.max(visibleMessageCount, 0));
}

/** Returns the renderer hot-session view for one full desktop chat session. */
export function createHotChatSession(
  session: SessionPayload,
  visibleMessageCount = hotChatSessionMessageCount,
): SessionPayload {
  const startIndex = getHotChatSessionStartIndex(session.messages.length, visibleMessageCount);
  if (startIndex === 0) {
    return session;
  }
  return {
    ...session,
    messages: session.messages.slice(startIndex),
  };
}

/** Returns how many older messages stay in the cold session while the renderer shows the hot tail. */
export function countHiddenHotChatMessages(
  fullSession: SessionPayload | null,
  hotSession: SessionPayload | null,
): number {
  if (!fullSession || !hotSession) {
    return 0;
  }
  return Math.max(0, fullSession.messages.length - hotSession.messages.length);
}

/** Expands the hot session upward by one fixed step from the cached full session. */
export function expandHotChatSession(
  fullSession: SessionPayload,
  hotSession: SessionPayload | null,
  step = hotChatSessionMessageCountStep,
): SessionPayload {
  const currentVisibleMessageCount = hotSession?.messages.length ?? 0;
  return createHotChatSession(fullSession, currentVisibleMessageCount + step);
}

/** Expands the hot session just enough to include one target message from the cold history. */
export function ensureHotChatSessionContainsMessage(
  fullSession: SessionPayload,
  hotSession: SessionPayload | null,
  messageKey: string,
): SessionPayload {
  const normalizedMessageKey = messageKey.trim();
  if (!normalizedMessageKey) {
    return hotSession ?? createHotChatSession(fullSession);
  }

  const currentHotSession = hotSession ?? createHotChatSession(fullSession);
  const fullMessageIndex = fullSession.messages.findIndex((message, index) => getChatMessageDomKey(message, index) === normalizedMessageKey);
  if (fullMessageIndex < 0) {
    return currentHotSession;
  }

  const hotStartIndex = Math.max(0, fullSession.messages.length - currentHotSession.messages.length);
  if (fullMessageIndex >= hotStartIndex) {
    return currentHotSession;
  }

  return createHotChatSession(
    fullSession,
    fullSession.messages.length - fullMessageIndex + highlightedChatMessageTrailingContext,
  );
}
