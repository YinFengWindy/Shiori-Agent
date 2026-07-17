import type React from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";

type UseRightSidebarStateArgs = {
  minWidth: number;
  maxWidth: number;
  defaultWidth: number;
  animationDurationMs: number;
  defaultCollapsed?: boolean;
};

function clampSidebarWidth(nextWidth: number, minWidth: number, maxWidth: number): number {
  return Math.min(maxWidth, Math.max(minWidth, nextWidth));
}

/** Manages a resizable right sidebar with persisted width, collapse state, and drag interactions. */
export function useRightSidebarState({
  minWidth,
  maxWidth,
  defaultWidth,
  animationDurationMs,
  defaultCollapsed = false,
}: UseRightSidebarStateArgs) {
  const collapseThreshold = minWidth / 2;
  const [width, setWidth] = useState(defaultWidth);
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const [animating, setAnimating] = useState(false);
  const [resizing, setResizing] = useState(false);
  const resizeFrameRef = useRef<number | null>(null);
  const pendingWidthRef = useRef<number | null>(null);

  const toggle = useCallback(() => {
    setAnimating(true);
    if (collapsed) {
      setWidth((current) => clampSidebarWidth(current, minWidth, maxWidth));
      setCollapsed(false);
      return;
    }
    setCollapsed(true);
  }, [collapsed, maxWidth, minWidth]);

  const open = useCallback(() => {
    setAnimating(true);
    setCollapsed(false);
    setWidth((current) => clampSidebarWidth(current, minWidth, maxWidth));
  }, [maxWidth, minWidth]);

  const beginResize = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    flushSync(() => {
      setAnimating(false);
      setResizing(true);
    });
    let dragCollapsed = collapsed;

    function flushPendingWidth(): void {
      if (resizeFrameRef.current !== null) {
        window.cancelAnimationFrame(resizeFrameRef.current);
        resizeFrameRef.current = null;
      }
      if (pendingWidthRef.current === null) {
        return;
      }
      setWidth(pendingWidthRef.current);
      pendingWidthRef.current = null;
    }

    function scheduleWidth(nextWidth: number): void {
      pendingWidthRef.current = nextWidth;
      if (resizeFrameRef.current !== null) {
        return;
      }
      resizeFrameRef.current = window.requestAnimationFrame(() => {
        resizeFrameRef.current = null;
        if (pendingWidthRef.current === null) {
          return;
        }
        setWidth(pendingWidthRef.current);
        pendingWidthRef.current = null;
      });
    }

    function stopResize(): void {
      flushPendingWidth();
      setResizing(false);
      window.removeEventListener("pointermove", resize);
      window.removeEventListener("pointerup", stopResize);
      window.removeEventListener("pointercancel", stopResize);
    }

    function resize(moveEvent: PointerEvent): void {
      const nextWidth = window.innerWidth - moveEvent.clientX;
      if (nextWidth <= collapseThreshold) {
        if (!dragCollapsed) {
          setAnimating(true);
          dragCollapsed = true;
        }
        setCollapsed(true);
        return;
      }
      if (dragCollapsed) {
        setAnimating(true);
        dragCollapsed = false;
      }
      scheduleWidth(clampSidebarWidth(nextWidth, minWidth, maxWidth));
    }

    window.addEventListener("pointermove", resize);
    window.addEventListener("pointerup", stopResize);
    window.addEventListener("pointercancel", stopResize);
  }, [collapsed, collapseThreshold, maxWidth, minWidth]);

  useEffect(() => {
    if (!animating) return undefined;
    const timer = window.setTimeout(() => setAnimating(false), animationDurationMs + 40);
    return () => window.clearTimeout(timer);
  }, [animating, animationDurationMs]);

  return {
    width,
    collapsed,
    animating,
    resizing,
    toggle,
    open,
    beginResize,
  };
}
