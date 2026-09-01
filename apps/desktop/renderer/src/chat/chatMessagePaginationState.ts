import { getVisibleChatMessages } from "./chatMessageWindow";
import type { SessionPayload } from "../shared/types";

/** Chooses either the server-backed loaded history or the legacy local render window. */
export function getPaginatedChatMessageWindow(
  session: SessionPayload | null,
  visibleMessageCount: number,
) {
  const messages = session?.messages ?? [];
  if (!session?.pagination) {
    return getVisibleChatMessages(messages, visibleMessageCount);
  }
  return {
    startIndex: 0,
    hiddenMessageCount: Math.max(0, session.pagination.total_count - messages.length),
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
