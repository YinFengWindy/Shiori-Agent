import { cx, focusResetClass } from "../shared/styles";

/** Shared surface for every chat-sidebar view. */
export const chatSidebarPanelClass =
  "grid h-full min-h-0 rounded-md border border-[#E1E7EF] bg-[#F5F7FA] px-3 pb-3 pt-2 text-sm text-[#334155] shadow-[0_8px_24px_rgba(15,23,42,0.04)]";

/** Shared compact header for task list, detail, and form views. */
export const chatSidebarHeaderClass =
  "flex min-h-11 items-center border-b border-[#E1E7EF] pl-1 pr-8";

/** Shared scroll container for task-sidebar content. */
export const chatSidebarScrollableClass =
  "scrollbar-soft min-h-0 overflow-y-auto py-3";

/** Shared back-navigation control for nested task views. */
export const chatSidebarBackButtonClass = cx(
  "grid h-8 w-8 shrink-0 place-items-center rounded-md text-[#5B6472] transition-colors hover:bg-white hover:text-[#272536]",
  focusResetClass,
);
