import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type React from "react";
import { getChatMessageDomKey, getChatMessageReactKey } from "./chatMessageIdentity";
import {
  getVirtualChatMessageWindow,
} from "./chatMessageVirtualization";
import { useChatMessageMeasurements } from "./useChatMessageMeasurements";
import type { SessionMessage } from "../shared/types";

type UseChatMessageVirtualizationArgs = {
  sessionKey: string;
  messages: SessionMessage[];
  messageStartIndex: number;
  highlightedMessageKey: string;
  conversationListRef: React.RefObject<HTMLDivElement | null>;
  isAutoScrollingRef: React.RefObject<boolean>;
  onMessageNavigationTargetMounted?: (messageKey: string, target: HTMLElement) => void;
  onContentSizeChange?: () => void;
};

type Viewport = {
  scrollTop: number;
  height: number;
};

function readViewport(container: HTMLDivElement): Viewport {
  return { scrollTop: container.scrollTop, height: container.clientHeight };
}

/** Owns bounded DOM rendering and measured spacer heights for a loaded chat-message page. */
export function useChatMessageVirtualization({
  sessionKey,
  messages,
  messageStartIndex,
  highlightedMessageKey,
  conversationListRef,
  isAutoScrollingRef,
  onMessageNavigationTargetMounted,
  onContentSizeChange,
}: UseChatMessageVirtualizationArgs) {
  // The first paint follows the chat's bottom-anchored startup behavior; the
  // mounted container is read immediately after commit and takes over.
  const [viewport, setViewport] = useState<Viewport>({ scrollTop: Number.POSITIVE_INFINITY, height: 0 });
  const contentSizeFrameRef = useRef<number | null>(null);
  const messageKeys = useMemo(
    () => messages.map((message, index) => getChatMessageReactKey(message, messageStartIndex + index)),
    [messageStartIndex, messages],
  );
  const pinnedMessageIndex = useMemo(
    () => messages.findIndex((message, index) => (
      getChatMessageDomKey(message, messageStartIndex + index) === highlightedMessageKey
    )),
    [highlightedMessageKey, messageStartIndex, messages],
  );
  const refreshViewport = useCallback(() => {
    const container = conversationListRef.current;
    if (!container) return;
    const next = readViewport(container);
    setViewport((current) => (
      current.scrollTop === next.scrollTop && current.height === next.height ? current : next
    ));
  }, [conversationListRef]);

  const requestContentSizeChange = useCallback(() => {
    if (!onContentSizeChange || typeof window === "undefined") return;
    if (contentSizeFrameRef.current !== null) return;
    contentSizeFrameRef.current = window.requestAnimationFrame(() => {
      contentSizeFrameRef.current = null;
      onContentSizeChange();
    });
  }, [onContentSizeChange]);

  const { measuredHeights, observeMessageElement } = useChatMessageMeasurements({
    sessionKey, highlightedMessageKey, conversationListRef, isAutoScrollingRef,
    onMessageNavigationTargetMounted, requestContentSizeChange,
  });

  const virtualMessageWindow = useMemo(
    () => getVirtualChatMessageWindow({
      messages,
      messageKeys,
      measuredHeights,
      scrollTop: viewport.scrollTop,
      viewportHeight: viewport.height,
      pinnedMessageIndex,
    }),
    [measuredHeights, messageKeys, messages, pinnedMessageIndex, viewport],
  );

  useEffect(() => {
    const container = conversationListRef.current;
    if (!container) return undefined;
    refreshViewport();
    const resizeObserver = new ResizeObserver(refreshViewport);
    resizeObserver.observe(container);
    container.addEventListener("scroll", refreshViewport, { passive: true });
    return () => {
      resizeObserver.disconnect();
      container.removeEventListener("scroll", refreshViewport);
    };
  }, [conversationListRef, refreshViewport, sessionKey]);

  useLayoutEffect(() => {
    requestContentSizeChange();
  }, [requestContentSizeChange, sessionKey]);

  useEffect(() => () => {
    if (contentSizeFrameRef.current !== null) {
      window.cancelAnimationFrame(contentSizeFrameRef.current);
      contentSizeFrameRef.current = null;
    }
  }, []);

  return { virtualMessageWindow, observeMessageElement };
}
