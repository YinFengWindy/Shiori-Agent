type ChatModelMenuAnchorRect = Pick<DOMRect, "left" | "top">;

/** Space kept between the menu and any window edge. */
const viewportMargin = 8;

/**
 * Positions the model menu above its button, kept inside the window: the
 * left edge is clamped so a narrow window never pushes the panel off-screen,
 * and `maxHeight` is the room above the button so a long model list scrolls
 * inside the panel instead of running past the top.
 */
export function getChatModelMenuPosition(
  anchor: ChatModelMenuAnchorRect,
  viewport: { width: number; height: number },
  menuWidth: number,
  gap = 4,
) {
  return {
    left: Math.max(viewportMargin, Math.min(anchor.left, viewport.width - menuWidth - viewportMargin)),
    bottom: viewport.height - anchor.top + gap,
    maxHeight: Math.max(120, anchor.top - gap - viewportMargin),
  };
}
