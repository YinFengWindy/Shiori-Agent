import { cx, focusResetClass } from "../shared/styles";

/** Shared surface for every chat-sidebar view. */
export const chatSidebarPanelClass =
  "grid h-full min-h-0 rounded-md border border-white/70 bg-white/70 px-3 pb-3 pt-2 text-sm text-ink-secondary shadow-soft backdrop-blur-md";

/** Shared compact header for task list, detail, and form views. */
export const chatSidebarHeaderClass =
  "flex min-h-11 items-center border-b border-line-soft pl-1 pr-8";

/** Shared scroll container for task-sidebar content. */
export const chatSidebarScrollableClass =
  "scrollbar-stable min-h-0 overflow-y-auto py-3";

/** Shared back-navigation control for nested task views. */
export const chatSidebarBackButtonClass = cx(
  "grid h-8 w-8 shrink-0 place-items-center rounded-md text-ink-muted transition-colors hover:bg-white hover:text-ink",
  focusResetClass,
);
