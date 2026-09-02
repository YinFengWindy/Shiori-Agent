import { useCallback, useEffect, useLayoutEffect, useRef } from "react";
import type React from "react";
import {
  getChatScrollAnimationDuration,
  getChatScrollAnimationTop,
  getChatScrollMaxTop,
} from "./chatScrollController";

type UseChatScrollControllerArgs = {
  conversationListRef: React.RefObject<HTMLDivElement | null>;
  sessionKey: string;
};

/** Owns interruptible bottom scrolling so virtual row measurement cannot cancel a long jump. */
export function useChatScrollController({
  conversationListRef,
  sessionKey,
}: UseChatScrollControllerArgs) {
  const animationFrameRef = useRef<number | null>(null);
  const isAutoScrollingRef = useRef(false);
  const expectedScrollTopRef = useRef<number | null>(null);

  const cancelAnimation = useCallback(() => {
    if (animationFrameRef.current !== null && typeof window !== "undefined") {
      window.cancelAnimationFrame(animationFrameRef.current);
    }
    animationFrameRef.current = null;
    expectedScrollTopRef.current = null;
    isAutoScrollingRef.current = false;
  }, []);

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
      return;
    }

    if (typeof window === "undefined") return;
    cancelAnimation();
    const startTop = container.scrollTop;
    const distance = Math.max(0, getChatScrollMaxTop(container) - startTop);
    if (distance <= 1) {
      expectedScrollTopRef.current = getChatScrollMaxTop(container);
      container.scrollTop = getChatScrollMaxTop(container);
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
        cancelAnimation();
        return;
      }
      animationFrameRef.current = window.requestAnimationFrame(animate);
    };

    animationFrameRef.current = window.requestAnimationFrame(animate);
  }, [cancelAnimation, conversationListRef]);

  useEffect(() => {
    const container = conversationListRef.current;
    if (!container) return undefined;

    const interruptAnimation = () => cancelAnimation();
    const handleScroll = () => {
      if (!isAutoScrollingRef.current) return;
      const expectedScrollTop = expectedScrollTopRef.current;
      if (expectedScrollTop === null || Math.abs(container.scrollTop - expectedScrollTop) > 1) {
        cancelAnimation();
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
  }, [cancelAnimation, conversationListRef, sessionKey]);

  useLayoutEffect(() => cancelAnimation, [cancelAnimation, sessionKey]);

  return { isAutoScrollingRef, scrollToBottom };
}
