import {
  compactButtonSizeClass,
  compactPressableClass,
  cx,
  pressableClass,
  primaryButtonSurfaceClass,
} from "@shiori/plugin-sdk";

/*
 * Class names plugins also use are owned by `@shiori/plugin-sdk` (#440) and
 * re-exported here, so host code keeps one import site; everything below the
 * re-export is host-only.
 */
export {
  badgeClass,
  cardClass,
  compactButtonSizeClass,
  compactGhostButtonClass,
  compactPressableClass,
  cx,
  ghostButtonClass,
  ghostButtonSurfaceClass,
  iconButtonClass,
  inputClass,
  pressableClass,
  primaryButtonSurfaceClass,
  secondarySidebarSurfaceClass,
  sidebarContentMotionClass,
  sidebarNavItemClass,
  textareaClass,
} from "@shiori/plugin-sdk";

/** Track of a segmented tab group: secondary navigation nested under a page's section tabs. */
export const segmentedTabListClass = "rounded-md bg-surface-soft p-1";

/**
 * One tab of a segmented group (role asset modes, memory views); visually
 * subordinate to `underlineTabClass`. The selected tab lifts onto the surface;
 * only colors transition.
 */
export function segmentedTabClass(selected: boolean) {
  return cx(
    "h-8 shrink-0 rounded-md px-3 text-body-sm transition-colors duration-quick",
    selected ? "bg-surface font-medium text-ink shadow-soft" : "text-ink-muted hover:text-ink",
  );
}

/**
 * Underlined in-page section tab (role detail sections). The row that
 * holds these tabs sits on a bottom border and uses `-mb-px` so the active
 * underline covers it.
 */
export function underlineTabClass(selected: boolean) {
  return cx(
    "h-10 shrink-0 border-b-2 px-1 text-body transition-colors",
    selected ? "border-accent font-medium text-ink" : "border-transparent text-ink-muted hover:text-ink",
  );
}

/** Shared small-body text class for non-titlebar desktop content. */
export const bodyTextClass = "text-body-sm";

/**
 * Sidebar open/close. The track animates its width (the only way to push the
 * main pane over), so it stays short and rides the drawer curve; the content
 * (`sidebarContentMotionClass`) keeps its own fixed width and only
 * fades/slides, which never relayouts. Under reduced motion the width jumps
 * and the content only fades.
 */
export const sidebarTrackMotionClass =
  "transition-[width] duration-panel ease-drawer motion-reduce:transition-none";

/** Size-free quiet destructive surface; see `primaryButtonSurfaceClass`. */
export const dangerGhostButtonSurfaceClass = cx(
  pressableClass,
  "cursor-pointer rounded-md border border-line bg-surface text-danger-text hover:border-danger/40 hover:bg-danger-soft disabled:cursor-default disabled:opacity-50",
);

/** Compact primary action button (surface + compact size). */
export const compactPrimaryButtonClass = cx(primaryButtonSurfaceClass, compactButtonSizeClass);

/** Compact quiet destructive button (surface + compact size). */
export const compactDangerGhostButtonClass = cx(dangerGhostButtonSurfaceClass, compactButtonSizeClass);

/**
 * Size-free borderless text button surface, for quiet footer actions that
 * should not compete with the section's main button (account danger zone).
 */
export const textButtonSurfaceClass = cx(
  pressableClass,
  "cursor-pointer rounded-md border border-transparent bg-transparent text-ink-secondary hover:bg-surface-hover hover:text-ink disabled:cursor-default disabled:opacity-50",
);

/** Size-free borderless destructive text surface; see `textButtonSurfaceClass`. */
export const dangerTextButtonSurfaceClass = cx(
  pressableClass,
  "cursor-pointer rounded-md border border-transparent bg-transparent text-danger-text hover:bg-danger-soft disabled:cursor-default disabled:opacity-50",
);

/** Compact borderless text button (surface + compact size). */
export const compactTextButtonClass = cx(textButtonSurfaceClass, compactButtonSizeClass);

/** Compact borderless destructive text button (surface + compact size). */
export const compactDangerTextButtonClass = cx(dangerTextButtonSurfaceClass, compactButtonSizeClass);

/** Shared primary action button styling. */
export const primaryButtonClass = cx(primaryButtonSurfaceClass, "px-[18px] py-3");

/** Shared destructive action button styling. */
export const dangerButtonClass = cx(
  pressableClass,
  "cursor-pointer rounded-md border border-transparent bg-danger px-[18px] py-3 text-white hover:brightness-105 active:brightness-95 disabled:cursor-default disabled:opacity-50",
);

/** Shared quiet destructive styling for inline delete affordances. */
export const dangerGhostButtonClass = cx(dangerGhostButtonSurfaceClass, "px-[18px] py-3");

/**
 * Borderless 28px icon-only button (dismiss, back, header toggles), for
 * places where iconButtonClass's bordered 40px tile would be too heavy.
 * Its icon is h-4 w-4.
 */
export const compactIconButtonClass = cx(
  compactPressableClass,
  "grid h-7 w-7 shrink-0 place-items-center rounded-md text-ink-muted hover:bg-surface-hover hover:text-ink",
);

/** Shared focus reset for controls that rely on their existing state styling. */
export const focusResetClass = "focus:outline-none";

/** Reusable panel header layout. */
export const panelHeadClass = "panel-head mb-3 flex items-center justify-between";

/** Reusable display-face panel title. */
export const panelTitleClass = "m-0 font-display text-title text-ink";

/** Native checkbox tinted with the accent color. */
export const checkboxClass = "h-4 w-4 accent-accent";

/** The dimmed, blurred backdrop behind a modal dialog (Base UI `Dialog.Backdrop`), fading with `motion-backdrop`. */
export const dialogBackdropClass = "confirm-dialog-backdrop motion-backdrop fixed inset-0 z-50 bg-ink/30 backdrop-blur-sm";
