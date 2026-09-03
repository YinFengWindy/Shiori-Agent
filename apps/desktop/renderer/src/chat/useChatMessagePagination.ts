import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import type React from "react";
import {
  getExpandedVisibleChatMessageCountForKey,
  initialVisibleChatMessageCount,
  visibleChatMessageCountStep,
} from "./chatMessageWindow";
import {
  getPaginatedChatMessageWindow,
  getPrependAnchorScrollTop,
  shouldLoadOlderChatMessages,
} from "./chatMessagePaginationState";
import type { SessionPayload } from "../shared/types";

const emptySessionMessages: SessionPayload["messages"] = [];

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
  const messages = activeSession?.messages ?? emptySessionMessages;
  const hasServerPagination = Boolean(activeSession?.pagination);
  const loading = loadingSessionKey === sessionKey;
  const loadingGateRef = useRef("");

  useLayoutEffect(() => {
    setVisibleMessageCount(initialVisibleChatMessageCount);
    anchorRef.current = null;
    setLoadingSessionKey("");
    loadingGateRef.current = "";
  }, [sessionKey]);

  const visibleMessageWindow = useMemo(
    () => getPaginatedChatMessageWindow(activeSession, visibleMessageCount),
    [activeSession, visibleMessageCount],
  );
  const canLoadOlderMessages = hasServerPagination
    ? Boolean(activeSession?.pagination?.has_more)
    : visibleMessageWindow.hiddenMessageCount > 0;

  const loadOlderPage = useCallback(() => {
    const container = conversationListRef.current;
    if (!container || !sessionKey || loading || !canLoadOlderMessages || loadingGateRef.current === sessionKey) return;
    loadingGateRef.current = sessionKey;
    anchorRef.current = {
      sessionKey,
      scrollHeight: container.scrollHeight,
      scrollTop: container.scrollTop,
    };
    if (hasServerPagination) {
      setLoadingSessionKey(sessionKey);
      void loadOlderMessages(sessionKey).finally(() => {
        setLoadingSessionKey((current) => current === sessionKey ? "" : current);
        if (loadingGateRef.current === sessionKey) loadingGateRef.current = "";
      });
      return;
    }
    setVisibleMessageCount((current) => current + visibleChatMessageCountStep);
  }, [canLoadOlderMessages, conversationListRef, hasServerPagination, loadOlderMessages, loading, sessionKey]);

  const maybeLoadOlderMessages = useCallback((scrollTop: number, isAutoScrolling: boolean) => {
    if (!shouldLoadOlderChatMessages({
      scrollTop,
      canLoadOlderMessages,
      loading,
      isAutoScrolling,
    })) return;
    loadOlderPage();
  }, [canLoadOlderMessages, loadOlderPage, loading]);

  useLayoutEffect(() => {
    if (!hasServerPagination && loadingGateRef.current === sessionKey) {
      loadingGateRef.current = "";
    }
  }, [hasServerPagination, sessionKey, visibleMessageCount]);

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
  }, [conversationListRef, loading, messages.length, sessionKey, visibleMessageWindow.startIndex]);

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
    canLoadOlderMessages,
    maybeLoadOlderMessages,
  };
}
