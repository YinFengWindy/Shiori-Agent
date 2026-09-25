/** Joins conditional Tailwind class names without pulling in a runtime dependency. */
export function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

/** Shared card surface used by empty states and diagnostic rows. */
export const cardClass = "rounded-lg border border-line-soft bg-surface shadow-soft";

/** Shared background for secondary workspace navigation sidebars: transparent so the app gradient shows through, matching the chat role sidebar. */
export const secondarySidebarSurfaceClass = "bg-transparent";

/** Shared interaction styling for sidebar navigation entries. */
export const sidebarNavItemClass =
  "rounded-md transition-colors hover:bg-surface-hover focus-visible:bg-surface-hover";

/** Shared small-body text class for non-titlebar desktop content. */
export const bodyTextClass = "text-body-sm";

/** Shared input styling for form controls outside the chat composer. */
export const inputClass =
  "w-full rounded-md border border-line bg-surface px-3.5 py-2.5 text-body text-ink transition placeholder:text-ink-faint hover:border-line-strong";

/** Shared textarea styling for role prompt fields. */
export const textareaClass = cx(inputClass, "min-h-24 resize-y");

/**
 * Press feedback: a small scale-down while the pointer is held, released on
 * the same curve so rapid clicks retarget mid-flight instead of snapping. It
 * owns the element's whole transition list (colors, shadow, filter, opacity
 * and transform), so it replaces rather than sits beside other `transition*`
 * classes. The scale is motion-safe only; reduced motion keeps the color feedback.
 */
const pressTransitionClass =
  "transition-[color,background-color,border-color,box-shadow,filter,opacity,transform] duration-quick ease-out-soft";

/** Press feedback for buttons and icon buttons larger than 30px. */
export const pressableClass = cx(pressTransitionClass, "motion-safe:enabled:active:scale-97");

/** Press feedback for compact icon buttons (30px and below), where 0.97 would not read. */
export const compactPressableClass = cx(pressTransitionClass, "motion-safe:enabled:active:scale-96");

/**
 * Sidebar open/close. The track animates its width (the only way to push the
 * main pane over), so it stays short and rides the drawer curve; the content
 * keeps its own fixed width and only fades/slides, which never relayouts.
 * Under reduced motion the width jumps and the content only fades.
 */
export const sidebarTrackMotionClass =
  "transition-[width] duration-panel ease-drawer motion-reduce:transition-none";

/** Companion to sidebarTrackMotionClass for the sidebar's own content. */
export const sidebarContentMotionClass =
  "transition-[opacity,transform] duration-base ease-out-soft motion-reduce:transition-opacity motion-reduce:transform-none";

/**
 * Button surfaces without size. The full-size classes below add the default
 * padding; a compact button composes a surface with `compactButtonSizeClass`
 * instead of overriding the default padding (an override is unreliable: both
 * utilities land on the element and the stylesheet order decides).
 */
export const primaryButtonSurfaceClass = cx(
  pressableClass,
  "cursor-pointer rounded-md border border-white/70 bg-gradient-accent text-ink shadow-soft hover:brightness-[1.03] hover:shadow-panel active:brightness-[0.97] disabled:cursor-default disabled:opacity-50 disabled:shadow-none",
);

/** Size-free secondary button surface; see `primaryButtonSurfaceClass`. */
export const ghostButtonSurfaceClass = cx(
  pressableClass,
  "cursor-pointer rounded-md border border-line bg-surface text-ink-secondary hover:border-line-accent hover:bg-accent-softer hover:text-accent-text disabled:cursor-default disabled:opacity-50",
);

/** Size-free quiet destructive surface; see `primaryButtonSurfaceClass`. */
export const dangerGhostButtonSurfaceClass = cx(
  pressableClass,
  "cursor-pointer rounded-md border border-line bg-surface text-danger-text hover:border-danger/40 hover:bg-danger-soft disabled:cursor-default disabled:opacity-50",
);

/** Height, padding and type of a compact (36px) labeled button; compose it with a surface class. */
export const compactButtonSizeClass = "inline-flex h-9 shrink-0 items-center justify-center gap-1.5 px-3.5 text-body-sm font-medium";

/** Shared primary action button styling. */
export const primaryButtonClass = cx(primaryButtonSurfaceClass, "px-[18px] py-3");

/** Shared secondary action button styling. */
export const ghostButtonClass = cx(ghostButtonSurfaceClass, "px-[18px] py-3");

/** Shared destructive action button styling. */
export const dangerButtonClass = cx(
  pressableClass,
  "cursor-pointer rounded-md border border-transparent bg-danger px-[18px] py-3 text-white hover:brightness-105 active:brightness-95 disabled:cursor-default disabled:opacity-50",
);

/** Shared quiet destructive styling for inline delete affordances. */
export const dangerGhostButtonClass = cx(dangerGhostButtonSurfaceClass, "px-[18px] py-3");

/** Square icon-only action button (back, reset, tools): the one corner treatment for this role is rounded-md. */
export const iconButtonClass = cx(
  pressableClass,
  "grid h-10 w-10 shrink-0 place-items-center rounded-md border border-line bg-surface text-ink-secondary hover:border-line-strong hover:bg-surface-hover disabled:cursor-default disabled:opacity-40",
);

/** Shared focus reset for controls that rely on their existing state styling. */
export const focusResetClass = "focus:outline-none";

/** Reusable panel header layout. */
export const panelHeadClass = "panel-head mb-3 flex items-center justify-between";

/** Reusable display-face panel title. */
export const panelTitleClass = "m-0 font-display text-title text-ink";

/** Native checkbox tinted with the accent color. */
export const checkboxClass = "h-4 w-4 accent-accent";

/** Soft pill badge for statuses and tags. */
export const badgeClass =
  "inline-flex items-center gap-1 rounded-full bg-accent-soft px-2.5 py-0.5 text-caption text-accent-text";
