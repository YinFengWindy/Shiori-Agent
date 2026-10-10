/**
 * Pure scroll ↔ line logic for the home page narrative (#771), with no DOM
 * so it is unit-testable.
 *
 * Layout it models (site.css): the narrative section is `lineCount + 1`
 * viewport heights tall and holds a sticky, one-viewport stage. It has one
 * step, and one scroll-snap point, per line — step `i` sits
 * `i × viewportHeight` below the section top — and then one final step,
 * `lineCount`, the download state on the same stage. The stage is pinned
 * from offset 0 to `lineCount × viewportHeight`; past that the page
 * scrolls on to whatever follows the narrative.
 *
 * Keyboard and the scrollbar scroll natively and CSS snapping lands them on
 * a line. The wheel is stepped by script (`narrativeStepTarget`,
 * `createWheelGestureGate`): Chromium snaps a short wheel or trackpad scroll
 * back to where it started, so one wheel notch alone would never move a
 * line. Touch scrolls natively too, and when the finger lifts the script
 * settles a swipe one line on from where it began (`narrativeStepTarget`), so
 * a short swipe does not snap back. Either way the line on screen is derived
 * from where the page is (`narrativeLineAt`).
 */

/** Where the page is relative to the narrative section. */
export interface NarrativeScroll {
  /** How far the section top has scrolled above the viewport top, in px (negative while the section is still below it). */
  readonly offset: number;
  /** One scroll step: the stage's (= one snap interval's) height, in px. */
  readonly viewportHeight: number;
  readonly lineCount: number;
}

function assertValid({ offset, viewportHeight, lineCount }: NarrativeScroll) {
  if (!Number.isInteger(lineCount) || lineCount < 1) throw new Error(`lineCount must be a positive integer, got ${lineCount}`);
  if (!(viewportHeight > 0)) throw new Error(`viewportHeight must be positive, got ${viewportHeight}`);
  if (!Number.isFinite(offset)) throw new Error(`offset must be finite, got ${offset}`);
}

/**
 * The step on stage at `offset`: `0 … lineCount - 1` is that line,
 * `lineCount` the download state. It is the nearest snap point, so the step
 * flips halfway between two points whichever way the page is moving. Before
 * the section it is the first line; past the download state's point (the
 * content after the narrative) it stays the download state.
 */
export function narrativeStepAt(scroll: NarrativeScroll): number {
  assertValid(scroll);
  const nearest = Math.round(scroll.offset / scroll.viewportHeight);
  return Math.min(scroll.lineCount, Math.max(0, nearest));
}

/**
 * The offset to scroll to for one step in `direction` (1 = on to the next
 * step, −1 = back), or `null` where the narrative does not step and the
 * browser should scroll as usual: above the first line, onward from the
 * download state (into the content after the narrative), or with the section
 * out of reach. Stepping on from the last line lands on the download state;
 * stepping back from it lands on the last line.
 */
export function narrativeStepTarget(scroll: NarrativeScroll, direction: 1 | -1): number | null {
  assertValid(scroll);
  const { offset, viewportHeight, lineCount } = scroll;
  const finalOffset = lineCount * viewportHeight;
  // Sub-pixel slack: a snapped offset can be fractional on zoomed pages.
  if (offset < -viewportHeight / 2 || offset > finalOffset + 1) return null;
  const target = Math.round(offset / viewportHeight) + direction;
  if (target < 0 || target > lineCount) return null;
  return target * viewportHeight;
}

/**
 * One step per wheel gesture. A wheel event starts a new gesture when the
 * previous one came at least `quietMs` earlier, so separate mouse-wheel
 * notches each step, while a fast spin or a trackpad swipe with its momentum
 * tail — a dense stream of events — steps once. Feed it every wheel event's
 * timestamp; it answers whether this event steps.
 */
export function createWheelGestureGate(quietMs = 180) {
  let lastEventAt = Number.NEGATIVE_INFINITY;
  return (now: number) => {
    const startsGesture = now - lastEventAt >= quietMs;
    lastEventAt = now;
    return startsGesture;
  };
}
