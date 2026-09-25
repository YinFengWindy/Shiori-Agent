/** Approximate menu footprint used to keep the menu inside the window. */
const menuWidthPx = 148;
const menuHeightPx = 120;

/** Least distance kept from the window's top/left edges. */
const edgePx = 12;

/** Gap between a message bubble and a menu opened from the keyboard under it. */
const keyboardGapPx = 4;

type Viewport = { width: number; height: number };

/** `aria-keyshortcuts` value for a focusable message: the keys that open its menu. */
export const chatMessageContextMenuKeyShortcuts = "Shift+F10 ContextMenu";

/** Whether a keydown is the keyboard's "open context menu" gesture (the menu key or Shift+F10). */
export function isChatMessageContextMenuKey(event: { key: string; shiftKey: boolean }): boolean {
  return event.key === "ContextMenu" || (event.key === "F10" && event.shiftKey);
}

/** Keeps the menu's top-left corner where the whole menu still fits in the window. */
export function clampChatMessageContextMenuPoint(point: { x: number; y: number }, viewport: Viewport) {
  return {
    x: Math.max(edgePx, Math.min(point.x, viewport.width - menuWidthPx)),
    y: Math.max(edgePx, Math.min(point.y, viewport.height - menuHeightPx)),
  };
}

/**
 * Where a menu opened from the keyboard goes: there is no pointer, so it sits
 * just under the start of the message bubble, clamped into the window (a long
 * message can run past the top or bottom of the viewport).
 */
export function getKeyboardChatMessageContextMenuPoint(
  bubble: Pick<DOMRect, "left" | "bottom">,
  viewport: Viewport,
) {
  return clampChatMessageContextMenuPoint({ x: bubble.left, y: bubble.bottom + keyboardGapPx }, viewport);
}
