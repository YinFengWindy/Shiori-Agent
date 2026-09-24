/**
 * The left sidebar's open/closed model — one source of truth for the title
 * bar toggle, the track width and the sidebar content.
 *
 * Two inputs never overwrite each other:
 * - `preferredCollapsed` is the user's own choice, only ever changed by the
 *   user (toggle, drag) or by opening a workspace whose navigation lives in
 *   the sidebar (settings, roles, plugin pages).
 * - `compact` is the window being narrower than the shell breakpoint. While
 *   compact the sidebar stops taking layout width and becomes an overlay
 *   drawer (`overlayOpen`), opened from the same toggle and closed by
 *   navigating, Escape or clicking outside. Leaving compact restores the
 *   preference untouched, so a collapse "caused" by a small window never
 *   follows the user back to a large one.
 */
export type SidebarLayoutState = {
  preferredCollapsed: boolean;
  compact: boolean;
  overlayOpen: boolean;
};

/** Everything that can change the sidebar layout. */
export type SidebarLayoutAction =
  | { type: "toggle" }
  | { type: "set-compact"; compact: boolean }
  /** A workspace that needs its sidebar was opened. */
  | { type: "reveal" }
  | { type: "dismiss-overlay" }
  /** A drag crossed the collapse threshold. */
  | { type: "drag"; collapsed: boolean };

/** Window widths below this (px) switch the shell to the compact, overlay-sidebar layout. */
export const compactShellBreakpoint = 1024;

/** Whether a window this wide uses the compact layout. */
export function isCompactShellWidth(windowWidth: number, breakpoint = compactShellBreakpoint): boolean {
  return windowWidth < breakpoint;
}

/** Initial layout for a window of the given width. */
export function initialSidebarLayout(windowWidth: number, breakpoint = compactShellBreakpoint): SidebarLayoutState {
  return { preferredCollapsed: false, compact: isCompactShellWidth(windowWidth, breakpoint), overlayOpen: false };
}

/** Whether the sidebar is effectively closed right now (what the toggle and the content show). */
export function isSidebarCollapsed(state: SidebarLayoutState): boolean {
  return state.compact ? !state.overlayOpen : state.preferredCollapsed;
}

/** Applies one layout action; returns the same object when nothing changes. */
export function reduceSidebarLayout(state: SidebarLayoutState, action: SidebarLayoutAction): SidebarLayoutState {
  switch (action.type) {
    case "toggle":
      return state.compact
        ? { ...state, overlayOpen: !state.overlayOpen }
        : { ...state, preferredCollapsed: !state.preferredCollapsed };
    case "set-compact":
      // Crossing the breakpoint either way closes a transient overlay.
      return state.compact === action.compact ? state : { ...state, compact: action.compact, overlayOpen: false };
    case "reveal":
      // A compact window keeps its drawer closed; the toggle still reaches it.
      return state.compact || !state.preferredCollapsed ? state : { ...state, preferredCollapsed: false };
    case "dismiss-overlay":
      return state.overlayOpen ? { ...state, overlayOpen: false } : state;
    case "drag":
      if (state.compact) {
        return state.overlayOpen === !action.collapsed ? state : { ...state, overlayOpen: !action.collapsed };
      }
      return state.preferredCollapsed === action.collapsed ? state : { ...state, preferredCollapsed: action.collapsed };
  }
}
