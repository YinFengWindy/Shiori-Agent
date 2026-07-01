import type React from "react";
import { useEffect, useState } from "react";
import { flushSync } from "react-dom";

type UseRightSidebarStateArgs = {
  minWidth: number;
  maxWidth: number;
  defaultWidth: number;
  animationDurationMs: number;
  defaultCollapsed?: boolean;
};

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

  function clampWidth(nextWidth: number): number {
    return Math.min(maxWidth, Math.max(minWidth, nextWidth));
  }

  function toggle(): void {
    setAnimating(true);
    if (collapsed) {
      setWidth((current) => clampWidth(current));
      setCollapsed(false);
      return;
    }
    setCollapsed(true);
  }

  function open(): void {
    setAnimating(true);
    setCollapsed(false);
    setWidth((current) => clampWidth(current));
  }

  function beginResize(event: React.PointerEvent<HTMLDivElement>): void {
    event.preventDefault();
    flushSync(() => {
      setAnimating(false);
      setResizing(true);
    });
    let dragCollapsed = collapsed;

    function stopResize(): void {
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
      setCollapsed(false);
      setWidth(clampWidth(nextWidth));
    }

    window.addEventListener("pointermove", resize);
    window.addEventListener("pointerup", stopResize);
    window.addEventListener("pointercancel", stopResize);
  }

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
