import { cx } from "@yinfengwindy/shiori-sdk";
import { focusResetClass } from "../shared/styles";

// The surfaces are shared with plugin blocks that render into the chat sidebar.
export { chatSidebarHeaderClass, chatSidebarPanelClass, chatSidebarScrollableClass } from "@yinfengwindy/shiori-sdk";

/** Shared back-navigation control for nested task views. */
export const chatSidebarBackButtonClass = cx(
  "grid h-8 w-8 shrink-0 place-items-center rounded-md text-ink-muted transition-colors hover:bg-white hover:text-ink",
  focusResetClass,
);
