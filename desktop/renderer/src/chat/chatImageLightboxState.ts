const minChatImageZoom = 1;
const maxChatImageZoom = 4;
const chatImageZoomStep = 0.2;

/** Clamps the lightbox zoom so the default fit-to-screen view is always reachable. */
export function clampChatImageZoom(zoom: number): number {
  return Math.min(maxChatImageZoom, Math.max(minChatImageZoom, zoom));
}

/** Computes the next zoom level from a wheel gesture. Negative delta zooms in; positive delta zooms out. */
export function getNextChatImageZoom(currentZoom: number, deltaY: number): number {
  if (deltaY === 0) {
    return clampChatImageZoom(currentZoom);
  }
  const zoomDelta = deltaY < 0 ? chatImageZoomStep : -chatImageZoomStep;
  return clampChatImageZoom(currentZoom + zoomDelta);
}
