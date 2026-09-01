import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type React from "react";
import { getChatMessageDomKey, getChatMessageReactKey } from "./chatMessageIdentity";
import {
  estimateChatMessageHeight,
  getVirtualChatMessageWindow,
} from "./chatMessageVirtualization";
import type { SessionMessage } from "../shared/types";

type UseChatMessageVirtualizationArgs = {
  sessionKey: string;
  messages: SessionMessage[];
  messageStartIndex: number;
  highlightedMessageKey: string;
  conversationListRef: React.RefObject<HTMLDivElement | null>;
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
  onContentSizeChange,
}: UseChatMessageVirtualizationArgs) {
  // The first paint follows the chat's bottom-anchored startup behavior; the
  // mounted container is read immediately after commit and takes over.
  const [viewport, setViewport] = useState<Viewport>({ scrollTop: Number.POSITIVE_INFINITY, height: 0 });
  const measurementsRef = useRef(new Map<string, number>());
  const [measuredHeights, setMeasuredHeights] = useState(() => new Map<string, number>());
  const observersRef = useRef(new Map<string, ResizeObserver>());
  const firstVisibleIndexRef = useRef(0);
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

  useLayoutEffect(() => {
    firstVisibleIndexRef.current = virtualMessageWindow.firstVisibleIndex;
  }, [virtualMessageWindow.firstVisibleIndex]);

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
    measurementsRef.current.clear();
    observersRef.current.forEach((observer) => observer.disconnect());
    observersRef.current.clear();
    setMeasuredHeights(new Map());
    requestContentSizeChange();
  }, [requestContentSizeChange, sessionKey]);

  useEffect(() => () => {
    if (contentSizeFrameRef.current !== null) {
      window.cancelAnimationFrame(contentSizeFrameRef.current);
      contentSizeFrameRef.current = null;
    }
    observersRef.current.forEach((observer) => observer.disconnect());
    observersRef.current.clear();
  }, []);

  const updateMeasuredHeight = useCallback((message: SessionMessage, index: number, height: number) => {
    const messageKey = getChatMessageReactKey(message, index);
    const nextHeight = Math.max(1, Math.ceil(height));
    const previousHeight = measurementsRef.current.get(messageKey) ?? estimateChatMessageHeight(message);
    if (Math.abs(nextHeight - previousHeight) < 1) return;
    measurementsRef.current.set(messageKey, nextHeight);
    setMeasuredHeights((current) => {
      if (current.get(messageKey) === nextHeight) return current;
      const next = new Map(current);
      next.set(messageKey, nextHeight);
      return next;
    });
    const localIndex = index - messageStartIndex;
    if (localIndex < firstVisibleIndexRef.current) {
      const container = conversationListRef.current;
      if (container) {
        container.scrollTop += nextHeight - previousHeight;
      }
    }
    requestContentSizeChange();
  }, [conversationListRef, messageStartIndex, requestContentSizeChange]);

  const observeMessageElement = useCallback((
    message: SessionMessage,
    index: number,
    element: HTMLElement | null,
  ) => {
    const messageKey = getChatMessageReactKey(message, index);
    observersRef.current.get(messageKey)?.disconnect();
    observersRef.current.delete(messageKey);
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const height = entries[0]?.contentRect.height;
      if (height != null) {
        updateMeasuredHeight(message, index, height);
      }
    });
    observersRef.current.set(messageKey, observer);
    observer.observe(element);
    updateMeasuredHeight(message, index, element.getBoundingClientRect().height);
  }, [updateMeasuredHeight]);

  return { virtualMessageWindow, observeMessageElement };
}
