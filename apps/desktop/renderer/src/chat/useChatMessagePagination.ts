import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type React from "react";
import {
  getExpandedVisibleChatMessageCountForKey,
  initialVisibleChatMessageCount,
  visibleChatMessageCountStep,
} from "./chatMessageWindow";
import {
  getPaginatedChatMessageWindow,
  getPrependAnchorScrollTop,
} from "./chatMessagePaginationState";
import type { SessionPayload } from "../shared/types";

type UseChatMessagePaginationArgs = {
  activeSession: SessionPayload | null;
  conversationListRef: React.RefObject<HTMLDivElement | null>;
  highlightedMessageKey: string;
  loadOlderMessages: (sessionKey: string) => Promise<boolean>;
};

/** Owns chat history paging and keeps the first visible message anchored after a prepend. */
export function useChatMessagePagination({
  activeSession,
  conversationListRef,
  highlightedMessageKey,
  loadOlderMessages,
}: UseChatMessagePaginationArgs) {
  const [visibleMessageCount, setVisibleMessageCount] = useState(initialVisibleChatMessageCount);
  const [loadingSessionKey, setLoadingSessionKey] = useState("");
  const anchorRef = useRef<{ sessionKey: string; scrollHeight: number; scrollTop: number } | null>(null);
  const sessionKey = activeSession?.key ?? "";
  const messages = activeSession?.messages ?? [];
  const hasServerPagination = Boolean(activeSession?.pagination);
  const loading = loadingSessionKey === sessionKey;

  useEffect(() => {
    setVisibleMessageCount(initialVisibleChatMessageCount);
    anchorRef.current = null;
    setLoadingSessionKey("");
  }, [sessionKey]);

  const visibleMessageWindow = useMemo(
    () => getPaginatedChatMessageWindow(activeSession, visibleMessageCount),
    [activeSession, visibleMessageCount],
  );

  const handleExpandOlderMessages = useCallback(() => {
    if (hasServerPagination) {
      const container = conversationListRef.current;
      if (!container || !sessionKey || loading) return;
      anchorRef.current = {
        sessionKey,
        scrollHeight: container.scrollHeight,
        scrollTop: container.scrollTop,
      };
      setLoadingSessionKey(sessionKey);
      void loadOlderMessages(sessionKey).finally(() => {
        setLoadingSessionKey((current) => current === sessionKey ? "" : current);
      });
      return;
    }
    setVisibleMessageCount((current) => current + visibleChatMessageCountStep);
  }, [conversationListRef, hasServerPagination, loadOlderMessages, loading, sessionKey]);

  useLayoutEffect(() => {
    const anchor = anchorRef.current;
    const container = conversationListRef.current;
    if (!anchor || !container || anchor.sessionKey !== sessionKey || loading) return;
    container.scrollTop = getPrependAnchorScrollTop(
      anchor.scrollHeight,
      anchor.scrollTop,
      container.scrollHeight,
    );
    anchorRef.current = null;
  }, [conversationListRef, loading, messages.length, sessionKey]);

  useLayoutEffect(() => {
    if (hasServerPagination) return;
    const nextVisibleMessageCount = getExpandedVisibleChatMessageCountForKey(
      messages,
      visibleMessageCount,
      highlightedMessageKey,
    );
    if (nextVisibleMessageCount !== visibleMessageCount) {
      setVisibleMessageCount(nextVisibleMessageCount);
    }
  }, [hasServerPagination, highlightedMessageKey, messages, visibleMessageCount]);

  return {
    visibleMessageWindow,
    loading,
    canLoadOlderMessages: hasServerPagination
      ? Boolean(activeSession?.pagination?.has_more)
      : visibleMessageWindow.hiddenMessageCount > 0,
    onLoadOlderMessages: handleExpandOlderMessages,
  };
}
