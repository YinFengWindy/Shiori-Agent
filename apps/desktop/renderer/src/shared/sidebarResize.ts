/** Clamps a sidebar width to its supported range. */
export function clampSidebarWidth(nextWidth: number, minWidth: number, maxWidth: number): number {
  return Math.min(maxWidth, Math.max(minWidth, nextWidth));
}

/** Returns whether a resize crossed the sidebar collapse boundary. */
export function hasSidebarCollapseChanged(previousCollapsed: boolean, nextCollapsed: boolean): boolean {
  return previousCollapsed !== nextCollapsed;
}
