import { useMemo, useState } from "react";
import { nextIndex, pickInitialIndex, type RandomSource } from "./titleArtSelection";

/**
 * React wiring around the pure title-art index selection: a random starting
 * image per mount (one per visit), `advance()` to move to the next image
 * (wrapping), and `select()` for the dot indicators to jump directly.
 */
export function useTitleArtSelection(count: number, random: RandomSource = Math.random) {
  const [index, setIndex] = useState(() => pickInitialIndex(count, random));

  const api = useMemo(
    () => ({
      advance: () => setIndex((current) => nextIndex(current, count)),
      select: (target: number) => setIndex(Math.min(Math.max(target, 0), count - 1)),
    }),
    [count],
  );

  return { index, ...api };
}
