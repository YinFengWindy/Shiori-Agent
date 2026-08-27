/**
 * Captures the current scroll position before a controlled form update so the
 * role detail page can restore it after React re-renders the inputs.
 */
export function captureRoleDetailScrollTop(
  container: Pick<HTMLElement, "scrollTop"> | null,
): number | null {
  if (!container) return null;
  return container.scrollTop;
}

/**
 * Restores the role detail page scroll offset after a render that would
 * otherwise nudge the focused input upward inside the scroll container.
 */
export function restoreRoleDetailScrollTop(
  container: Pick<HTMLElement, "scrollTop"> | null,
  scrollTop: number | null,
): null {
  if (!container || scrollTop == null) return null;
  container.scrollTop = scrollTop;
  return null;
}
