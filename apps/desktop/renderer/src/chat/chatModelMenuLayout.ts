type ChatModelMenuAnchorRect = Pick<DOMRect, "left" | "top">;

/** Positions the menu above the model button with a stable visual gap. */
export function getChatModelMenuPosition(
  anchor: ChatModelMenuAnchorRect,
  viewportHeight: number,
  gap = 4,
) {
  return {
    left: anchor.left,
    bottom: viewportHeight - anchor.top + gap,
  };
}
