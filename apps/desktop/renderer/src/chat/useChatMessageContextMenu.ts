import { useCallback, useEffect, useRef, useState } from "react";
import type React from "react";
import type { MessageContextMenuState } from "./chatMessageActions";
import type { SessionMessage } from "../shared/types";

/** Approximate menu footprint used to keep the menu inside the window. */
const menuWidthPx = 148;
const menuHeightPx = 120;

/**
 * Owns the chat message right-click menu: where it opens (clamped to the
 * window) and every way it closes — outside pointer, scroll, resize, Escape.
 */
export function useChatMessageContextMenu() {
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [menu, setMenu] = useState<MessageContextMenuState | null>(null);
  const close = useCallback(() => setMenu(null), []);

  useEffect(() => {
    if (!menu) return undefined;
    const handlePointerDown = (event: PointerEvent) => {
      const panel = menuRef.current;
      if (panel && event.target instanceof Node && panel.contains(event.target)) return;
      close();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("pointerdown", handlePointerDown, true);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown, true);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [close, menu]);

  const open = useCallback((
    event: React.MouseEvent<HTMLElement>,
    message: SessionMessage,
    messageKey: string,
    sender: string,
  ) => {
    event.preventDefault();
    event.stopPropagation();
    setMenu({
      x: Math.min(event.clientX, Math.max(12, window.innerWidth - menuWidthPx)),
      y: Math.min(event.clientY, Math.max(12, window.innerHeight - menuHeightPx)),
      message,
      messageKey,
      sender,
    });
  }, []);

  return { menu, menuRef, open, close };
}
