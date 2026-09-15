import { useCallback, useLayoutEffect, useMemo, useState } from "react";
import type React from "react";
import { getChatMessageDomKey, getChatMessageReactKey } from "./chatMessageIdentity";
import { estimateChatMessageHeight } from "./chatMessageVirtualization";
import type { SessionMessage } from "../shared/types";

const emptyMeasurements = new Map<string, number>();

type SessionMeasurements = {
  heights: Map<string, number>;
  observers: Map<string, ResizeObserver>;
};

type Args = {
  sessionKey: string;
  highlightedMessageKey: string;
  conversationListRef: React.RefObject<HTMLDivElement | null>;
  isAutoScrollingRef: React.RefObject<boolean>;
  onMessageNavigationTargetMounted?: (messageKey: string, target: HTMLElement) => void;
  requestContentSizeChange: () => void;
};

/** Measures mounted rows and keeps observers and cached heights owned by their session. */
export function useChatMessageMeasurements({
  sessionKey, highlightedMessageKey, conversationListRef, isAutoScrollingRef,
  onMessageNavigationTargetMounted, requestContentSizeChange,
}: Args) {
  const [sessionCaches] = useState(() => new Map<string, SessionMeasurements>());
  const cache = useMemo(() => {
    let saved = sessionCaches.get(sessionKey);
    if (!saved) {
      saved = { heights: new Map(), observers: new Map() };
      sessionCaches.set(sessionKey, saved);
    }
    return saved;
  }, [sessionCaches, sessionKey]);
  const [measurementState, setMeasurementState] = useState(() => ({ cache, heights: emptyMeasurements }));
  // Saved scroll positions use these measured coordinates, including rows that
  // are currently virtualized away and cannot be measured again on restoration.
  const measuredHeights = measurementState.cache === cache ? measurementState.heights : cache.heights;
  // Cleanup closes only the outgoing session's observers. A setup effect must
  // never disconnect rows whose ref callbacks just attached in this commit.
  useLayoutEffect(() => () => {
    cache.observers.forEach((observer) => observer.disconnect());
    cache.observers.clear();
  }, [cache]);

  const updateMeasuredHeight = useCallback((
    message: SessionMessage,
    index: number,
    height: number,
    element: HTMLElement,
  ) => {
    const messageKey = getChatMessageReactKey(message, index);
    const nextHeight = Math.max(1, Math.ceil(height));
    const previousHeight = cache.heights.get(messageKey) ?? estimateChatMessageHeight(message);
    if (Math.abs(nextHeight - previousHeight) < 1) return;
    cache.heights.set(messageKey, nextHeight);
    setMeasurementState((current) => {
      if (current.cache === cache && current.heights.get(messageKey) === nextHeight) return current;
      return { cache, heights: new Map(cache.heights) };
    });
    const container = conversationListRef.current;
    const containerRect = container?.getBoundingClientRect();
    const elementRect = element.getBoundingClientRect();
    const isAboveViewport = Boolean(containerRect && elementRect.bottom <= containerRect.top);
    if (container && isAboveViewport && !isAutoScrollingRef.current) {
      container.scrollTop += nextHeight - previousHeight;
    }
    requestContentSizeChange();
  }, [cache, conversationListRef, isAutoScrollingRef, requestContentSizeChange]);

  const observeMessageElement = useCallback((
    message: SessionMessage,
    index: number,
    element: HTMLElement | null,
  ) => {
    const messageKey = getChatMessageReactKey(message, index);
    const domKey = getChatMessageDomKey(message, index);
    if (element && domKey === highlightedMessageKey) {
      onMessageNavigationTargetMounted?.(domKey, element);
    }
    cache.observers.get(messageKey)?.disconnect();
    cache.observers.delete(messageKey);
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const height = entries[0]?.contentRect.height;
      if (height != null) {
        updateMeasuredHeight(message, index, height, element);
      }
    });
    cache.observers.set(messageKey, observer);
    observer.observe(element);
    updateMeasuredHeight(message, index, element.getBoundingClientRect().height, element);
  }, [cache, highlightedMessageKey, onMessageNavigationTargetMounted, updateMeasuredHeight]);

  return { measuredHeights, observeMessageElement };
}
