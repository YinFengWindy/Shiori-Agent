import type React from "react";
import { useState } from "react";
import { flushSync } from "react-dom";
import { clampSidebarWidth, hasSidebarCollapseChanged } from "./sidebarResize";

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

  function toggle(): void {
    setAnimating(true);
    if (collapsed) {
      setWidth((current) => clampSidebarWidth(current, minWidth, maxWidth));
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
        if (hasSidebarCollapseChanged(dragCollapsed, true)) {
          setAnimating(true);
          dragCollapsed = true;
        }
        setCollapsed(true);
        return;
      }
      if (hasSidebarCollapseChanged(dragCollapsed, false)) {
        setAnimating(true);
        dragCollapsed = false;
      }
      setCollapsed(false);
      setWidth(clampSidebarWidth(moveEvent.clientX, minWidth, maxWidth));
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
