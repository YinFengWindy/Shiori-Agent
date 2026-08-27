import type React from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { clampSidebarWidth, hasSidebarCollapseChanged } from "./sidebarResize";

type UseRightSidebarStateArgs = {
  minWidth: number;
  maxWidth: number;
  defaultWidth: number;
  animationDurationMs: number;
  defaultCollapsed?: boolean;
};

/** Resolves one right-sidebar drag sample without scheduling a React update. */
export function resolveRightSidebarDragUpdate(
  clientX: number,
  viewportWidth: number,
  minWidth: number,
  maxWidth: number,
  collapseThreshold: number,
) {
  const requestedWidth = viewportWidth - clientX;
  if (requestedWidth <= collapseThreshold) {
    return {
      collapsed: true,
      previewWidth: 0,
      expandedWidth: null,
    };
  }
  const expandedWidth = clampSidebarWidth(requestedWidth, minWidth, maxWidth);
  return {
    collapsed: false,
    previewWidth: expandedWidth,
    expandedWidth,
  };
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
    const sidebarElement = event.currentTarget.parentElement;
    if (!sidebarElement) return;
    const resizeTarget = sidebarElement;
    flushSync(() => {
      setAnimating(false);
      setResizing(true);
    });
    let dragCollapsed = collapsed;
    let committedWidth = width;

    function flushPendingPreviewWidth(): void {
      if (resizeFrameRef.current !== null) {
        window.cancelAnimationFrame(resizeFrameRef.current);
        resizeFrameRef.current = null;
      }
      if (pendingWidthRef.current === null) {
        return;
      }
      resizeTarget.style.width = `${pendingWidthRef.current}px`;
      pendingWidthRef.current = null;
    }

    function schedulePreviewWidth(nextWidth: number): void {
      pendingWidthRef.current = nextWidth;
      if (resizeFrameRef.current !== null) {
        return;
      }
      resizeFrameRef.current = window.requestAnimationFrame(() => {
        resizeFrameRef.current = null;
        if (pendingWidthRef.current === null) {
          return;
        }
        resizeTarget.style.width = `${pendingWidthRef.current}px`;
        pendingWidthRef.current = null;
      });
    }

    function stopResize(): void {
      flushPendingPreviewWidth();
      setWidth(committedWidth);
      setCollapsed(dragCollapsed);
      setResizing(false);
      window.removeEventListener("pointermove", resize);
      window.removeEventListener("pointerup", stopResize);
      window.removeEventListener("pointercancel", stopResize);
    }

    function resize(moveEvent: PointerEvent): void {
      const update = resolveRightSidebarDragUpdate(
        moveEvent.clientX,
        window.innerWidth,
        minWidth,
        maxWidth,
        collapseThreshold,
      );
      const previousCollapsed = dragCollapsed;
      dragCollapsed = update.collapsed;
      if (hasSidebarCollapseChanged(previousCollapsed, update.collapsed)) {
        setAnimating(true);
      }
      if (update.expandedWidth !== null) {
        committedWidth = update.expandedWidth;
      }
      schedulePreviewWidth(update.previewWidth);
    }

    window.addEventListener("pointermove", resize);
    window.addEventListener("pointerup", stopResize);
    window.addEventListener("pointercancel", stopResize);
  }, [collapsed, collapseThreshold, maxWidth, minWidth, width]);

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
