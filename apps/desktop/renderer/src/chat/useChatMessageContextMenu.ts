import { useCallback, useEffect, useRef, useState } from "react";
import type React from "react";
import type { MessageContextMenuState } from "./chatMessageActions";
import {
  clampChatMessageContextMenuPoint,
  getKeyboardChatMessageContextMenuPoint,
} from "./chatMessageContextMenuPlacement";
import type { SessionMessage } from "../shared/types";

/**
 * Owns the chat message context menu: where it opens and every way it closes.
 *
 * It opens from a right-click (at the pointer) or from the keyboard on a
 * focused message — the menu key or Shift+F10, whether it arrives as the
 * keydown itself or as the `contextmenu` event the browser synthesizes for it
 * (`button === -1`). A keyboard-opened menu sits under the message bubble and
 * takes focus (see `ChatMessageContextMenu`); closing it after an action, on
 * Escape or on Tab hands focus back to the message. An outside pointer-down,
 * scroll or resize just dismisses it.
 */
export function useChatMessageContextMenu() {
  const menuRef = useRef<HTMLDivElement | null>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const [menu, setMenu] = useState<MessageContextMenuState | null>(null);

  const dismiss = useCallback(() => {
    returnFocusRef.current = null;
    setMenu(null);
  }, []);

  /** Closes the menu; one opened from the keyboard returns focus to its message. */
  const close = useCallback(() => {
    const origin = returnFocusRef.current;
    returnFocusRef.current = null;
    setMenu(null);
    if (origin?.isConnected) origin.focus({ preventScroll: true });
  }, []);

  useEffect(() => {
    if (!menu) return undefined;
    const handlePointerDown = (event: PointerEvent) => {
      const panel = menuRef.current;
      if (panel && event.target instanceof Node && panel.contains(event.target)) return;
      dismiss();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("pointerdown", handlePointerDown, true);
    window.addEventListener("scroll", dismiss, true);
    window.addEventListener("resize", dismiss);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown, true);
      window.removeEventListener("scroll", dismiss, true);
      window.removeEventListener("resize", dismiss);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [close, dismiss, menu]);

  const open = useCallback((
    event: React.MouseEvent<HTMLElement> | React.KeyboardEvent<HTMLElement>,
    message: SessionMessage,
    messageKey: string,
    sender: string,
  ) => {
    event.preventDefault();
    event.stopPropagation();
    const viewport = { width: window.innerWidth, height: window.innerHeight };
    const origin = event.currentTarget;
    const fromKeyboard = !("button" in event) || event.button === -1;
    const point = fromKeyboard
      ? getKeyboardChatMessageContextMenuPoint(
        (origin.querySelector(".message-bubble") ?? origin).getBoundingClientRect(),
        viewport,
      )
      : clampChatMessageContextMenuPoint({ x: event.clientX, y: event.clientY }, viewport);
    returnFocusRef.current = fromKeyboard ? origin : null;
    setMenu({ ...point, message, messageKey, sender, fromKeyboard });
  }, []);

  return { menu, menuRef, open, close };
}
