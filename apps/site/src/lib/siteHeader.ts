/**
 * When the home page's top bar shows (#773), with no DOM so it is
 * unit-testable. The bar stays out of the narrative, a full-screen stage
 * of its own, and slides in once the page has moved on to what follows it
 * (the showcase): when the narrative section's bottom edge has risen past
 * the middle of the viewport, i.e. the showcase fills most of the screen.
 * Scroll snapping only rests on the download state (the section's bottom at
 * the viewport's bottom) or the showcase's top (at the viewport's top), so
 * the middle is never a resting point the bar could flicker at.
 */
export function isPastNarrative(narrativeBottom: number, viewportHeight: number): boolean {
  if (!(viewportHeight > 0)) throw new Error(`viewportHeight must be positive, got ${viewportHeight}`);
  if (!Number.isFinite(narrativeBottom)) throw new Error(`narrativeBottom must be finite, got ${narrativeBottom}`);
  return narrativeBottom <= viewportHeight / 2;
}
