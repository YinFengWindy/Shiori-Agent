/**
 * Pure CG-lightbox state: which image is shown and whether the lightbox is
 * open, with wrap-around stepping. No DOM or React here — `useCgLightbox`
 * drives it and owns focus/sound. Closing keeps `index`, so the gallery knows
 * which thumbnail should get focus back.
 */

export interface LightboxState {
  readonly open: boolean;
  /** Currently (or last) shown image, always in `[0, count)`. */
  readonly index: number;
  readonly count: number;
}

function assertCount(count: number) {
  if (!Number.isInteger(count) || count <= 0) {
    throw new Error("count must be a positive integer");
  }
}

/** Wrap any integer (negative or past the end) into `[0, count)`. */
export function wrapIndex(index: number, count: number): number {
  assertCount(count);
  if (!Number.isInteger(index)) throw new Error("index must be an integer");
  return ((index % count) + count) % count;
}

/** A closed lightbox over `count` images, parked on the first one. */
export function createLightbox(count: number): LightboxState {
  assertCount(count);
  return { open: false, index: 0, count };
}

/** Open the lightbox on image `index` (must be in range — it comes from a thumbnail). */
export function openLightbox(state: LightboxState, index: number): LightboxState {
  if (!Number.isInteger(index) || index < 0 || index >= state.count) {
    throw new Error(`index ${index} is out of range for ${state.count} images`);
  }
  return { ...state, open: true, index };
}

/** Close the lightbox, remembering the image that was showing. */
export function closeLightbox(state: LightboxState): LightboxState {
  return state.open ? { ...state, open: false } : state;
}

/** Step `delta` images forward (or back), wrapping at both ends; a no-op while closed. */
export function stepLightbox(state: LightboxState, delta: number): LightboxState {
  if (!state.open) return state;
  return { ...state, index: wrapIndex(state.index + delta, state.count) };
}

/** Human counter for the shown image, e.g. "3 / 10". */
export function lightboxCounter(state: LightboxState): string {
  return `${state.index + 1} / ${state.count}`;
}
