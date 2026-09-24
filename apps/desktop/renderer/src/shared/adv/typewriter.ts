/**
 * Pure typewriter progress shared by every ADV dialogue (the site's 「开始」
 * screen and the desktop first-run guide). Time only moves through explicit
 * elapsed milliseconds, so reveals are deterministic and unit testable.
 */

/** How far one line has been typed out. */
export interface TypewriterProgress {
  /** Characters of the line revealed so far. */
  readonly shownChars: number;
  /** Elapsed time not yet converted into a whole character. */
  readonly pendingMs: number;
}

/** Timing for one reveal step. */
export interface TypewriterTiming {
  /** Typewriter speed; 0 or less shows the whole line at once. */
  readonly msPerChar: number;
  /** prefers-reduced-motion: every line is shown in full at once. */
  readonly reducedMotion: boolean;
}

/** Whether lines skip the typewriter entirely. */
export function isInstantReveal(timing: TypewriterTiming) {
  return timing.reducedMotion || timing.msPerChar <= 0;
}

/** Progress at the start of a line: empty, or already complete when instant. */
export function startTypewriter(lineLength: number, timing: TypewriterTiming): TypewriterProgress {
  return { shownChars: isInstantReveal(timing) ? lineLength : 0, pendingMs: 0 };
}

/**
 * Reveals as many characters as `elapsedMs` pays for, carrying the remainder.
 * Returns the same object when nothing changes, so reducers can skip renders.
 */
export function advanceTypewriter(progress: TypewriterProgress, elapsedMs: number, lineLength: number, timing: TypewriterTiming): TypewriterProgress {
  if (elapsedMs <= 0 || progress.shownChars >= lineLength) return progress;
  if (isInstantReveal(timing)) return { shownChars: lineLength, pendingMs: 0 };
  const total = progress.pendingMs + elapsedMs;
  const chars = Math.floor(total / timing.msPerChar);
  const shownChars = Math.min(lineLength, progress.shownChars + chars);
  return { shownChars, pendingMs: shownChars >= lineLength ? 0 : total - chars * timing.msPerChar };
}
