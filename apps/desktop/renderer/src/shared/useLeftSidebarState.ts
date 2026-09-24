import type React from "react";
import { useCallback, useEffect, useReducer, useState } from "react";
import { flushSync } from "react-dom";
import { clampSidebarWidth, hasSidebarCollapseChanged } from "./sidebarResize";
import {
  compactShellBreakpoint,
  initialSidebarLayout,
  isCompactShellWidth,
  isSidebarCollapsed,
  reduceSidebarLayout,
} from "./sidebarLayout";

type UseLeftSidebarStateArgs = {
  minWidth: number;
  maxWidth: number;
  defaultWidth: number;
  collapseThreshold: number;
  animationDurationMs: number;
  compactBreakpoint?: number;
};

/**
 * Resolves one left-sidebar drag sample from the grab offset.
 *
 * Deliberately expressed as "the width it had when you grabbed it, plus how
 * far the pointer has travelled since" rather than as the pointer's absolute
 * `clientX`. The sidebar does not start at the viewport's left edge — the nav
 * rail occupies the shell grid's first column — so treating `clientX` as the
 * width made the sidebar jump right by the rail's width the moment a drag
 * began. Measuring the delta keeps this correct no matter what sits to the
 * left of the track, how wide the grab handle is, or where inside it the
 * pointer landed.
 *
 * `startWidth` is the *rendered* width, so it is 0 while collapsed: dragging
 * the collapsed sidebar open then grows from nothing under the pointer
 * instead of snapping back to the width it had before it was collapsed.
 */
export function resolveLeftSidebarDragUpdate(
  startWidth: number,
  startX: number,
  clientX: number,
  minWidth: number,
  maxWidth: number,
  collapseThreshold: number,
) {
  const requestedWidth = startWidth + (clientX - startX);
  if (requestedWidth <= collapseThreshold) {
    return { collapsed: true, width: null };
  }
  return { collapsed: false, width: clampSidebarWidth(requestedWidth, minWidth, maxWidth) };
}

function currentWindowWidth(): number {
  return typeof window === "undefined" ? Number.POSITIVE_INFINITY : window.innerWidth;
}

/**
 * Manages the desktop shell's collapsible, resizable left sidebar. Open /
 * closed comes from the single layout model in `sidebarLayout.ts`: the
 * user's preference plus a responsive compact mode in which the sidebar
 * becomes an overlay drawer instead of being force-collapsed.
 */
export function useLeftSidebarState({
  minWidth,
  maxWidth,
  defaultWidth,
  collapseThreshold,
  animationDurationMs,
  compactBreakpoint = compactShellBreakpoint,
}: UseLeftSidebarStateArgs) {
  const [width, setWidth] = useState(defaultWidth);
  const [layout, dispatch] = useReducer(reduceSidebarLayout, undefined, () => initialSidebarLayout(currentWindowWidth(), compactBreakpoint));
  const [resizing, setResizing] = useState(false);
  const [animating, setAnimating] = useState(false);
  const collapsed = isSidebarCollapsed(layout);

  // Follow the window across the compact breakpoint.
  useEffect(() => {
    function syncCompact(): void {
      dispatch({ type: "set-compact", compact: isCompactShellWidth(window.innerWidth, compactBreakpoint) });
    }
    syncCompact();
    window.addEventListener("resize", syncCompact);
    return () => window.removeEventListener("resize", syncCompact);
  }, [compactBreakpoint]);

  // Escape closes the overlay drawer unless something above it (a dialog, a menu) already took the key.
  useEffect(() => {
    if (!layout.overlayOpen) return undefined;
    function closeOnEscape(event: KeyboardEvent): void {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      setAnimating(true);
      dispatch({ type: "dismiss-overlay" });
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [layout.overlayOpen]);

  useEffect(() => {
    if (!animating) return undefined;
    const timer = window.setTimeout(() => setAnimating(false), animationDurationMs + 40);
    return () => window.clearTimeout(timer);
  }, [animating, animationDurationMs]);

  const toggle = useCallback((): void => {
    setAnimating(true);
    setWidth((current) => clampSidebarWidth(current, minWidth, maxWidth));
    dispatch({ type: "toggle" });
  }, [maxWidth, minWidth]);

  /** Opens the sidebar for a workspace whose navigation lives there (a no-op in compact mode). */
  const reveal = useCallback((): void => {
    if (!layout.compact && layout.preferredCollapsed) setAnimating(true);
    setWidth((current) => clampSidebarWidth(current, minWidth, maxWidth));
    dispatch({ type: "reveal" });
  }, [layout.compact, layout.preferredCollapsed, maxWidth, minWidth]);

  /** Closes the compact overlay drawer, e.g. after the user navigated from it. */
  const dismissOverlay = useCallback((): void => {
    dispatch({ type: "dismiss-overlay" });
  }, []);

  function beginResize(event: React.PointerEvent<HTMLDivElement>): void {
    event.preventDefault();
    flushSync(() => {
      setAnimating(false);
      setResizing(true);
    });
    let dragCollapsed = collapsed;
    // Captured once, at the grab: everything below is relative to these.
    const startX = event.clientX;
    const startWidth = collapsed ? 0 : width;

    function stopResize(): void {
      setResizing(false);
      window.removeEventListener("pointermove", resize);
      window.removeEventListener("pointerup", stopResize);
      window.removeEventListener("pointercancel", stopResize);
    }

    function resize(moveEvent: PointerEvent): void {
      const update = resolveLeftSidebarDragUpdate(
        startWidth,
        startX,
        moveEvent.clientX,
        minWidth,
        maxWidth,
        collapseThreshold,
      );
      if (hasSidebarCollapseChanged(dragCollapsed, update.collapsed)) {
        setAnimating(true);
        dragCollapsed = update.collapsed;
      }
      dispatch({ type: "drag", collapsed: update.collapsed });
      if (update.width !== null) setWidth(update.width);
    }

    window.addEventListener("pointermove", resize);
    window.addEventListener("pointerup", stopResize);
    window.addEventListener("pointercancel", stopResize);
  }

  return {
    width,
    collapsed,
    /** Below the shell breakpoint: the sidebar overlays the main pane instead of taking width. */
    compact: layout.compact,
    resizing,
    animating,
    toggle,
    reveal,
    dismissOverlay,
    beginResize,
  };
}
