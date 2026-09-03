import { getVisibleChatMessages } from "./chatMessageWindow";
import type { SessionPayload } from "../shared/types";

export const chatMessagePaginationTopThreshold = 96;

/** Returns whether a user scroll near the top should request an older page. */
export function shouldLoadOlderChatMessages({
  scrollTop,
  canLoadOlderMessages,
  loading,
  isAutoScrolling,
}: {
  scrollTop: number;
  canLoadOlderMessages: boolean;
  loading: boolean;
  isAutoScrolling: boolean;
}): boolean {
  return scrollTop <= chatMessagePaginationTopThreshold
    && canLoadOlderMessages
    && !loading
    && !isAutoScrolling;
}

/** Invokes the older-page loader when a scroll event crosses the paging gates. */
export function triggerOlderChatMessagesLoad({
  scrollTop,
  canLoadOlderMessages,
  loading,
  loadingGateActive = false,
  isAutoScrolling,
  loadOlderPage,
}: {
  scrollTop: number;
  canLoadOlderMessages: boolean;
  loading: boolean;
  loadingGateActive?: boolean;
  isAutoScrolling: boolean;
  loadOlderPage: () => void;
}): boolean {
  if (loadingGateActive || !shouldLoadOlderChatMessages({
    scrollTop,
    canLoadOlderMessages,
    loading,
    isAutoScrolling,
  })) return false;
  loadOlderPage();
  return true;
}

/** Returns whether restoring a previously browsed session should check for older history. */
export function shouldLoadOlderChatMessagesAfterSessionRestore({
  scrollTop,
  restoredWasAtBottom,
  canLoadOlderMessages,
  loading,
}: {
  scrollTop: number;
  restoredWasAtBottom: boolean;
  canLoadOlderMessages: boolean;
  loading: boolean;
}): boolean {
  return !restoredWasAtBottom && shouldLoadOlderChatMessages({
    scrollTop,
    canLoadOlderMessages,
    loading,
    isAutoScrolling: false,
  });
}

/** Chooses either the server-backed loaded history or the legacy local render window. */
export function getPaginatedChatMessageWindow(
  session: SessionPayload | null,
  visibleMessageCount: number,
) {
  const messages = session?.messages ?? [];
  if (!session?.pagination) {
    return getVisibleChatMessages(messages, visibleMessageCount);
  }
  const loadedPersistedMessageCount = messages.reduce(
    (count, message) => count + (typeof message.seq === "number" ? 1 : 0),
    0,
  );
  return {
    startIndex: 0,
    hiddenMessageCount: Math.max(0, session.pagination.total_count - loadedPersistedMessageCount),
    messages,
  };
}

/** Restores the same visual message after older content was prepended above it. */
export function getPrependAnchorScrollTop(
  previousScrollHeight: number,
  previousScrollTop: number,
  currentScrollHeight: number,
): number {
  return previousScrollTop + (currentScrollHeight - previousScrollHeight);
}
