import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type React from "react";
import { chatScrollBottomThreshold } from "./chatScrollController";
import { listenForChatScrollIntent } from "./chatScrollIntent";
import { shouldAutoScrollOnContentSizeChange } from "./chatAutoScroll";
import { useLatestRef } from "../shared/useLatestRef";

type Args = {
  conversationListRef: React.RefObject<HTMLDivElement | null>;
  isAutoScrollingRef: React.RefObject<boolean>;
  sessionKey: string;
  highlightedMessageKey: string;
  scrollToBottom: (behavior: ScrollBehavior) => void;
  cancelScroll: () => void;
  maybeLoadOlderMessages: (scrollTop: number, isAutoScrolling: boolean) => void;
};

/** Keeps follow intent independent of layout changes and observes the current scroll viewport. */
export function useChatBottomFollow({
  conversationListRef, isAutoScrollingRef, sessionKey, highlightedMessageKey,
  scrollToBottom, cancelScroll, maybeLoadOlderMessages,
}: Args) {
  const stickToBottomRef = useRef(true);
  const previousTopRef = useRef(0);
  const [scrollState, setScrollState] = useState({ isAtBottom: true, isScrollable: false });
  const latest = useLatestRef({ highlightedMessageKey, maybeLoadOlderMessages });
  useLayoutEffect(() => {
    // Navigation remains paused after its temporary highlight disappears.
    if (highlightedMessageKey) stickToBottomRef.current = false;
  }, [highlightedMessageKey]);
  const scrollConversationToBottom = useCallback((behavior: ScrollBehavior) => {
    stickToBottomRef.current = true;
    scrollToBottom(behavior);
    previousTopRef.current = conversationListRef.current?.scrollTop ?? 0;
  }, [conversationListRef, scrollToBottom]);
  const handleChatContentSizeChange = useCallback(() => {
    if (shouldAutoScrollOnContentSizeChange({
      wasAtBottom: stickToBottomRef.current,
      highlightedMessageKey: latest.current.highlightedMessageKey,
    })) {
      scrollConversationToBottom("auto");
    }
  }, [latest, scrollConversationToBottom]);

  useEffect(() => {
    const container = conversationListRef.current;
    if (!container) return;
    previousTopRef.current = container.scrollTop;
    const updateScrollState = (fromScroll = false) => {
      const distance = container.scrollHeight - container.scrollTop - container.clientHeight;
      const next = {
        isAtBottom: distance <= chatScrollBottomThreshold,
        isScrollable: container.scrollHeight - container.clientHeight > chatScrollBottomThreshold,
      };
      // Only movement back down resumes a paused follower. Delayed programmatic
      // events at the old position must not override a just-received upward gesture.
      if (fromScroll && next.isAtBottom && container.scrollTop > previousTopRef.current
        && !latest.current.highlightedMessageKey) {
        stickToBottomRef.current = true;
      }
      previousTopRef.current = container.scrollTop;
      setScrollState((current) => current.isAtBottom === next.isAtBottom
        && current.isScrollable === next.isScrollable ? current : next);
    };
    const stopFollowing = () => {
      stickToBottomRef.current = false;
      cancelScroll();
    };
    const removeInputListeners = listenForChatScrollIntent(container, stopFollowing);
    const handleScroll = () => {
      updateScrollState(true);
      latest.current.maybeLoadOlderMessages(container.scrollTop, isAutoScrollingRef.current);
    };
    const handleResize = () => {
      handleChatContentSizeChange();
      updateScrollState();
    };
    updateScrollState();
    container.addEventListener("scroll", handleScroll, { passive: true });
    const observer = new ResizeObserver(handleResize);
    observer.observe(container);
    return () => {
      removeInputListeners();
      container.removeEventListener("scroll", handleScroll);
      observer.disconnect();
    };
  }, [cancelScroll, conversationListRef, handleChatContentSizeChange, isAutoScrollingRef, latest, sessionKey]);

  return { stickToBottomRef, scrollState, scrollConversationToBottom, handleChatContentSizeChange };
}
