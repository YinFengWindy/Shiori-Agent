import { prefersReducedMotion } from "./reducedMotion";

/** The CSS custom properties one tilt frame writes onto the card. */
export type TiltFrame = {
  /** Degrees around X: the top edge leans away when the pointer is near it. */
  rotateX: number;
  /** Degrees around Y: the side under the pointer leans away. */
  rotateY: number;
  /** Horizontal shift of the diagonal glare band, in % of its width. */
  glareX: number;
  /** Pointer position inside the card for the radial highlight, in %. */
  highlightX: number;
  highlightY: number;
};

const clamp01 = (value: number) => Math.min(1, Math.max(0, value));
const round = (value: number) => Math.round(value * 100) / 100;

/**
 * Maps a pointer position over a card to its tilt. The card leans at most
 * `maxDegrees` at an edge and sits flat at the centre; a pointer outside the
 * card (fast moves) is clamped to the nearest edge.
 */
export function tiltFromPointer(
  pointer: { x: number; y: number },
  rect: { left: number; top: number; width: number; height: number },
  maxDegrees = 8,
): TiltFrame {
  const px = rect.width > 0 ? clamp01((pointer.x - rect.left) / rect.width) : 0.5;
  const py = rect.height > 0 ? clamp01((pointer.y - rect.top) / rect.height) : 0.5;
  return {
    rotateX: round((0.5 - py) * 2 * maxDegrees),
    rotateY: round((px - 0.5) * 2 * maxDegrees),
    glareX: round((px - 0.5) * 50),
    highlightX: round(px * 100),
    highlightY: round(py * 100),
  };
}

/**
 * Tilt is a hover flourish: only for a fine pointer that can hover (a mouse),
 * and never under reduced motion.
 */
export function canTilt(pointerType: string): boolean {
  if (pointerType !== "mouse" || prefersReducedMotion()) return false;
  return typeof window !== "undefined"
    && typeof window.matchMedia === "function"
    && window.matchMedia("(hover: hover) and (pointer: fine)").matches;
}
