/** The part of the trigger button's rect the popover is placed against. */
export type ChatComposerPopoverAnchorRect = Pick<DOMRect, "left" | "right" | "top">;

/** Which edge of the trigger the popover lines up with. */
export type ChatComposerPopoverAlign = "start" | "end";

/** Space kept between a popover and any window edge. */
const viewportMargin = 8;

/** A popover never shrinks below this; shorter than that it would be useless. */
const minPopoverHeight = 120;

/**
 * Positions a composer popover (model menu, emoji panel) above its trigger in
 * window coordinates, for a `position: fixed` panel portalled to the body so
 * no clipping ancestor (the composer card is `overflow: hidden`) can cut it.
 *
 * - `align: "start"` lines the panel's left edge up with the trigger's, `"end"`
 *   its right edge with the trigger's right edge; either way the left edge is
 *   clamped so a narrow window never pushes the panel off-screen.
 * - `bottom` sits `gap` px above the trigger, so the panel grows upward.
 * - `maxHeight` is the room between the trigger and the top of the window: a
 *   short window makes the panel scroll inside itself instead of running off
 *   the top.
 */
export function getChatComposerPopoverPosition(
  anchor: ChatComposerPopoverAnchorRect,
  viewport: { width: number; height: number },
  popoverWidth: number,
  { align = "start", gap = 4 }: { align?: ChatComposerPopoverAlign; gap?: number } = {},
) {
  const preferredLeft = align === "end" ? anchor.right - popoverWidth : anchor.left;
  return {
    left: Math.max(viewportMargin, Math.min(preferredLeft, viewport.width - popoverWidth - viewportMargin)),
    bottom: viewport.height - anchor.top + gap,
    maxHeight: Math.max(minPopoverHeight, anchor.top - gap - viewportMargin),
  };
}

/** Result of `getChatComposerPopoverPosition`, applied as fixed-position inline style. */
export type ChatComposerPopoverPosition = ReturnType<typeof getChatComposerPopoverPosition>;
