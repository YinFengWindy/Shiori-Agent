/**
 * Shared menu vocabulary for every floating menu/popover panel (context
 * menus, model pickers, emoji panels, `Select` and `ActionMenu`). Positioning
 * stays with the caller; this owns only the look so menus read as one family.
 */

/** Floating panel surface. */
export const menuPanelClass =
  "rounded-md border border-line-soft bg-white/[0.98] p-1.5 shadow-pop backdrop-blur-md";

/** One interactive row inside a menu. */
export const menuItemClass =
  "flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-xs text-ink-secondary transition hover:bg-surface-hover hover:text-ink focus:bg-surface-hover focus:outline-none disabled:cursor-default disabled:opacity-45 disabled:hover:bg-transparent";

/** Applied on top of menuItemClass for the selected/current row. */
export const menuItemSelectedClass = "bg-accent-soft text-ink hover:bg-accent-soft";

/** Thin divider between groups. */
export const menuSeparatorClass = "my-1 h-px bg-line-soft";
