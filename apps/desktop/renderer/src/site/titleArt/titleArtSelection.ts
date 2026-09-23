/**
 * Pure title-art index selection: which of the title standing-art images is
 * shown, with no DOM/React/randomness baked in. `pickInitialIndex` takes an
 * injectable random source so tests can assert an exact starting index, and
 * `nextIndex` wraps around instead of running off the end of the array.
 */

/** Returns a float in [0, 1), matching the `Math.random` contract. */
export type RandomSource = () => number;

/** Uniformly pick a starting index in `[0, count)` from `random()`. */
export function pickInitialIndex(count: number, random: RandomSource = Math.random): number {
  if (!Number.isInteger(count) || count <= 0) {
    throw new Error("count must be a positive integer");
  }
  const roll = random();
  if (roll < 0 || roll >= 1) {
    throw new Error("random source must return a value in [0, 1)");
  }
  return Math.floor(roll * count);
}

/** Advance to the next index, wrapping back to 0 after the last one. */
export function nextIndex(current: number, count: number): number {
  if (!Number.isInteger(count) || count <= 0) {
    throw new Error("count must be a positive integer");
  }
  return (current + 1) % count;
}
