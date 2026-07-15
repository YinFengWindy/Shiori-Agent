import type React from "react";
import { useState } from "react";
import { flushSync } from "react-dom";

type UseLeftSidebarStateArgs = {
  minWidth: number;
  maxWidth: number;
  defaultWidth: number;
  collapseThreshold: number;
};

/** Manages the desktop shell's collapsible and resizable left sidebar. */
export function useLeftSidebarState({
  minWidth,
  maxWidth,
  defaultWidth,
  collapseThreshold,
}: UseLeftSidebarStateArgs) {
  const [width, setWidth] = useState(defaultWidth);
  const [collapsed, setCollapsed] = useState(false);
  const [resizing, setResizing] = useState(false);
  const [animating, setAnimating] = useState(false);

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
      if (moveEvent.clientX <= collapseThreshold) {
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
      setWidth(clampWidth(moveEvent.clientX));
    }

    window.addEventListener("pointermove", resize);
    window.addEventListener("pointerup", stopResize);
    window.addEventListener("pointercancel", stopResize);
  }

  return {
    width,
    collapsed,
    resizing,
    animating,
    setWidth,
    setCollapsed,
    setAnimating,
    toggle,
    beginResize,
  };
}
