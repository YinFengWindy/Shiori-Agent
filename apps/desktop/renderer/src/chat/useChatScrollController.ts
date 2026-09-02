import { useCallback, useEffect, useLayoutEffect, useRef } from "react";
import type React from "react";
import {
  getChatScrollAnimationDuration,
  getChatScrollAnimationTop,
  getChatScrollMaxTop,
  getChatScrollTargetTop,
  getChatSessionRestoreScrollTop,
  rememberChatSessionScrollState,
  type ChatSessionScrollState,
} from "./chatScrollController";

type UseChatScrollControllerArgs = {
  conversationListRef: React.RefObject<HTMLDivElement | null>;
  sessionKey: string;
};

/** Scrolls a mounted message and reports when its navigation animation settles. */
export type ChatMessageNavigationScroller = (
  target: HTMLElement,
  onSettled: () => void,
) => void;

/** Owns interruptible bottom scrolling so virtual row measurement cannot cancel a long jump. */
export function useChatScrollController({
  conversationListRef,
  sessionKey,
}: UseChatScrollControllerArgs) {
  const animationFrameRef = useRef<number | null>(null);
  const isAutoScrollingRef = useRef(false);
  const expectedScrollTopRef = useRef<number | null>(null);
  const animationSettledRef = useRef<(() => void) | null>(null);
  const sessionScrollStatesRef = useRef(new Map<string, ChatSessionScrollState>());
  const sessionKeyRef = useRef(sessionKey);

  const stopAnimation = useCallback((settle: boolean) => {
    if (animationFrameRef.current !== null && typeof window !== "undefined") {
      window.cancelAnimationFrame(animationFrameRef.current);
    }
    animationFrameRef.current = null;
    expectedScrollTopRef.current = null;
    isAutoScrollingRef.current = false;
    const onSettled = animationSettledRef.current;
    animationSettledRef.current = null;
    if (settle) {
      onSettled?.();
    }
  }, []);

  const cancelAnimation = useCallback(() => {
    stopAnimation(false);
  }, [stopAnimation]);

  const rememberSessionScroll = useCallback((targetSessionKey = sessionKeyRef.current) => {
    const container = conversationListRef.current;
    if (!container) return;
    rememberChatSessionScrollState(
      sessionScrollStatesRef.current,
      targetSessionKey,
      container.scrollTop,
      container.scrollHeight,
      container.clientHeight,
    );
  }, [conversationListRef]);

  useLayoutEffect(() => {
    if (sessionKeyRef.current !== sessionKey) {
      rememberSessionScroll(sessionKeyRef.current);
    }
    sessionKeyRef.current = sessionKey;
  }, [rememberSessionScroll, sessionKey]);

  const restoreSessionScroll = useCallback((targetSessionKey: string) => {
    const state = sessionScrollStatesRef.current.get(targetSessionKey);
    const container = conversationListRef.current;
    if (!state || !container) return null;
    cancelAnimation();
    container.scrollTop = getChatSessionRestoreScrollTop(
      state,
      container.scrollHeight,
      container.clientHeight,
    );
    return state;
  }, [cancelAnimation, conversationListRef]);

  const scrollToBottom = useCallback((behavior: ScrollBehavior) => {
    const container = conversationListRef.current;
    if (!container) return;

    // Measurements can arrive while the animation is running. The animation
    // reads the latest target on every frame, so an auto snap here would make
    // a long scroll visibly teleport.
    if (behavior === "auto") {
      if (isAutoScrollingRef.current) return;
      cancelAnimation();
      container.scrollTop = getChatScrollMaxTop(container);
      rememberSessionScroll();
      return;
    }

    if (typeof window === "undefined") return;
    stopAnimation(true);
    const startTop = container.scrollTop;
    const distance = Math.max(0, getChatScrollMaxTop(container) - startTop);
    if (distance <= 1) {
      expectedScrollTopRef.current = getChatScrollMaxTop(container);
      container.scrollTop = getChatScrollMaxTop(container);
      rememberSessionScroll();
      return;
    }

    const startedAt = window.performance.now();
    const duration = getChatScrollAnimationDuration(distance);
    isAutoScrollingRef.current = true;
    expectedScrollTopRef.current = startTop;

    const animate = (now: number) => {
      const currentContainer = conversationListRef.current;
      if (!currentContainer) {
        cancelAnimation();
        return;
      }
      const progress = Math.min(1, Math.max(0, (now - startedAt) / duration));
      const targetTop = getChatScrollMaxTop(currentContainer);
      const nextScrollTop = getChatScrollAnimationTop(startTop, targetTop, progress);
      expectedScrollTopRef.current = nextScrollTop;
      currentContainer.scrollTop = nextScrollTop;
      if (progress >= 1) {
        expectedScrollTopRef.current = getChatScrollMaxTop(currentContainer);
        currentContainer.scrollTop = getChatScrollMaxTop(currentContainer);
        rememberSessionScroll();
        stopAnimation(true);
        return;
      }
      animationFrameRef.current = window.requestAnimationFrame(animate);
    };

    animationFrameRef.current = window.requestAnimationFrame(animate);
  }, [cancelAnimation, conversationListRef, rememberSessionScroll, stopAnimation]);

  const scrollToMessage = useCallback<ChatMessageNavigationScroller>((target, onSettled) => {
    const container = conversationListRef.current;
    if (!container || typeof window === "undefined") {
      onSettled();
      return;
    }

    stopAnimation(true);
    const getTargetScrollTop = (currentContainer: HTMLDivElement) => {
      const containerRect = currentContainer.getBoundingClientRect();
      const targetRect = target.getBoundingClientRect();
      return getChatScrollTargetTop({
        currentScrollTop: currentContainer.scrollTop,
        containerTop: containerRect.top,
        containerHeight: currentContainer.clientHeight,
        targetTop: targetRect.top,
        targetHeight: targetRect.height,
        maxTop: getChatScrollMaxTop(currentContainer),
      });
    };
    const startTop = container.scrollTop;
    const initialTargetTop = getTargetScrollTop(container);
    const distance = Math.abs(initialTargetTop - startTop);
    if (distance <= 1) {
      container.scrollTop = initialTargetTop;
      onSettled();
      return;
    }

    const startedAt = window.performance.now();
    const duration = getChatScrollAnimationDuration(distance);
    animationSettledRef.current = onSettled;
    isAutoScrollingRef.current = true;
    expectedScrollTopRef.current = startTop;

    const animate = (now: number) => {
      const currentContainer = conversationListRef.current;
      if (!currentContainer || !target.isConnected) {
        stopAnimation(true);
        return;
      }
      const progress = Math.min(1, Math.max(0, (now - startedAt) / duration));
      const targetTop = getTargetScrollTop(currentContainer);
      const nextScrollTop = getChatScrollAnimationTop(startTop, targetTop, progress);
      expectedScrollTopRef.current = nextScrollTop;
      currentContainer.scrollTop = nextScrollTop;
      if (progress >= 1) {
        currentContainer.scrollTop = getTargetScrollTop(currentContainer);
        stopAnimation(true);
        return;
      }
      animationFrameRef.current = window.requestAnimationFrame(animate);
    };

    animationFrameRef.current = window.requestAnimationFrame(animate);
  }, [conversationListRef, stopAnimation]);

  useEffect(() => {
    const container = conversationListRef.current;
    if (!container) return undefined;

    const interruptAnimation = () => stopAnimation(true);
    const handleScroll = () => {
      rememberSessionScroll();
      if (!isAutoScrollingRef.current) return;
      const expectedScrollTop = expectedScrollTopRef.current;
      if (expectedScrollTop === null || Math.abs(container.scrollTop - expectedScrollTop) > 1) {
        stopAnimation(true);
      }
    };
    window.addEventListener("wheel", interruptAnimation, { passive: true });
    window.addEventListener("touchstart", interruptAnimation, { passive: true });
    window.addEventListener("pointerdown", interruptAnimation, { passive: true });
    container.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      window.removeEventListener("wheel", interruptAnimation);
      window.removeEventListener("touchstart", interruptAnimation);
      window.removeEventListener("pointerdown", interruptAnimation);
      container.removeEventListener("scroll", handleScroll);
    };
  }, [conversationListRef, rememberSessionScroll, stopAnimation]);

  // A session switch cancels the old animation; it must not settle its
  // navigation callback after the next session has started mounting.
  useLayoutEffect(() => cancelAnimation, [cancelAnimation, sessionKey]);

  return { isAutoScrollingRef, restoreSessionScroll, scrollToBottom, scrollToMessage };
}
