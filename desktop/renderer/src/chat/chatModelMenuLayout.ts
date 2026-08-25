type ChatModelMenuAnchorRect = Pick<DOMRect, "left" | "bottom">;

/** Positions the menu above the model button with a stable visual gap. */
export function getChatModelMenuPosition(
  anchor: ChatModelMenuAnchorRect,
  viewportHeight: number,
  gap = 4,
) {
  return {
    left: anchor.left,
    bottom: viewportHeight - anchor.bottom + gap,
  };
}
