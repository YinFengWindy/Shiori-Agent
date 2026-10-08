import { useCallback, useSyncExternalStore } from "react";
import { getChatDraft, subscribeChatDrafts } from "./chatDraftStore";

/** Keeps the visible composer subscribed to its session's memory-only draft. */
export function useChatDraft(key: string | null) {
  const getSnapshot = useCallback(() => getChatDraft(key), [key]);
  return useSyncExternalStore(subscribeChatDrafts, getSnapshot, getSnapshot);
}
