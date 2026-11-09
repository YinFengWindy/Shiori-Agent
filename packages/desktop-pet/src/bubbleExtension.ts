
/**
 * Where the pet's speech bubble goes, and how much window space it needs.
 *
 * This decision belongs to the plugin, not to the host: per the #181 design,
 * the host owns only what writes window bounds at frame rate (cursor follow,
 * release glide, eased moves) and knows nothing about speech bubbles. The
 * plugin measures its own bubble, asks the host for nothing but the work area
 * it was clamped into, and then requests a surface extension.
 *
 * Ported from the former main-process `resolveDesktopPetBubbleLayout`; the
 * tie-breaking is deliberately unchanged so a bubble does not start flipping
 * sides at positions where it used to stay put.
 */

/** Space between the sprite and its bubble, in CSS pixels. */
export const petBubbleGap = 6;

/** Which side of the sprite the bubble occupies, and its usable height. */
export type PetBubblePlacement = { placement: "above" | "below"; height: number };

/** No bubble at all: the window is exactly the sprite body. */
export const noPetBubble: PetBubblePlacement = { placement: "below", height: 0 };

/**
 * Chooses the side with room for the measured bubble, clamping it to fit.
 *
 * Prefers below — the bubble only flips above when it does not fit below *and*
 * there is genuinely more room up there. An oversized reply is truncated to
 * the chosen side rather than allowed off-screen; the bubble itself scrolls.
 */
export function resolvePetBubblePlacement(
  anchorY: number,
  workArea: { y: number; height: number },
  requestedHeight: number,
  bodyHeight: number,
): PetBubblePlacement {
  if (!Number.isFinite(requestedHeight)) return noPetBubble;
  const height = Math.max(0, Math.ceil(requestedHeight));
  if (!height) return noPetBubble;

  const below = Math.max(0, workArea.y + workArea.height - anchorY - bodyHeight - petBubbleGap);
  const above = Math.max(0, anchorY - workArea.y - petBubbleGap);
  if (height <= below || below >= above) {
    return { placement: "below", height: Math.min(height, below) };
  }
  return { placement: "above", height: Math.min(height, above) };
}

/**
 * Converts a bubble placement into the surface extension that makes room for it.
 *
 * The gap is part of the extension rather than of the bubble height so that the
 * bubble element's own measured height stays comparable across relayouts.
 */
export function petBubbleSurfaceExtension(
  placement: PetBubblePlacement,
): { side: "above" | "below"; size: number } {
  return {
    side: placement.placement,
    size: placement.height ? placement.height + petBubbleGap : 0,
  };
}

/** Whether two extensions are the same request, so a no-op resize can be skipped. */
export function isSamePetBubbleExtension(
  left: { side: string; size: number },
  right: { side: string; size: number },
): boolean {
  return left.side === right.side && left.size === right.size;
}
