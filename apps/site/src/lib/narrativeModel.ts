/**
 * Pure scroll ↔ line logic for the home page narrative (#771), with no DOM
 * so it is unit-testable.
 *
 * Layout it models (site.css): the narrative section is `lineCount` viewport
 * heights tall and holds a sticky, one-viewport stage; each line owns one
 * scroll-snap point, `index × viewportHeight` below the section top, and the
 * block after the narrative (the CTA) owns the next one, `lineCount ×
 * viewportHeight`. The stage is pinned while the offset runs from 0 to
 * `(lineCount - 1) × viewportHeight`.
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
 * Index of the line shown at `offset`: the nearest snap point, so the line
 * flips halfway between two points whichever way the page is moving. Before
 * the section it is the first line; past the last point — leaving for the CTA,
 * or coming back up from it — it stays the last line.
 */
export function narrativeLineAt(scroll: NarrativeScroll): number {
  assertValid(scroll);
  const nearest = Math.round(scroll.offset / scroll.viewportHeight);
  return Math.min(scroll.lineCount - 1, Math.max(0, nearest));
}

/**
 * The offset to scroll to for one wheel step in `direction` (1 = down to the
 * next line, −1 = back), or `null` where the narrative does not step and the
 * browser should scroll as usual: above the first line, below the CTA's top
 * (the free-scrolling content after it), or with the section out of reach.
 * Stepping down from the last line lands on the CTA; stepping up from the
 * CTA's top lands back on the last line.
 */
export function narrativeStepTarget(scroll: NarrativeScroll, direction: 1 | -1): number | null {
  assertValid(scroll);
  const { offset, viewportHeight, lineCount } = scroll;
  const exitOffset = lineCount * viewportHeight;
  // Sub-pixel slack: a snapped offset can be fractional on zoomed pages.
  if (offset < -viewportHeight / 2 || offset > exitOffset + 1) return null;
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
