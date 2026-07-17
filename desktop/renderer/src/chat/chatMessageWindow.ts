import { getChatMessageDomKey } from "./chatMessageIdentity";
import type { SessionMessage } from "../shared/types";

export const initialVisibleChatMessageCount = 60;
export const visibleChatMessageCountStep = 60;
const highlightedChatMessageTrailingContext = 24;

/** Returns the top slice index for the currently rendered chat message window. */
export function getVisibleChatMessageStartIndex(totalMessageCount: number, visibleMessageCount: number): number {
  if (totalMessageCount <= 0) {
    return 0;
  }
  return Math.max(0, totalMessageCount - Math.max(visibleMessageCount, 0));
}

/** Returns the current render window slice for desktop chat messages. */
export function getVisibleChatMessages(
  messages: SessionMessage[],
  visibleMessageCount: number,
): {
  startIndex: number;
  hiddenMessageCount: number;
  messages: SessionMessage[];
} {
  const startIndex = getVisibleChatMessageStartIndex(messages.length, visibleMessageCount);
  return {
    startIndex,
    hiddenMessageCount: startIndex,
    messages: messages.slice(startIndex),
  };
}

/** Expands the render window just enough to include one highlighted or navigated chat message. */
export function getExpandedVisibleChatMessageCountForKey(
  messages: SessionMessage[],
  visibleMessageCount: number,
  highlightedMessageKey: string,
): number {
  const normalizedMessageKey = highlightedMessageKey.trim();
  if (!normalizedMessageKey) {
    return visibleMessageCount;
  }

  const startIndex = getVisibleChatMessageStartIndex(messages.length, visibleMessageCount);
  const highlightedIndex = messages.findIndex((message, index) => getChatMessageDomKey(message, index) === normalizedMessageKey);
  if (highlightedIndex < 0 || highlightedIndex >= startIndex) {
    return visibleMessageCount;
  }

  return Math.max(
    visibleMessageCount,
    messages.length - highlightedIndex + highlightedChatMessageTrailingContext,
  );
}
