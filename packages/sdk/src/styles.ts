/**
 * Shared component class names of the Shiori design system that plugins use
 * (see docs/_handbook/design-system.md). The host imports these from here;
 * its `shared/styles.ts` holds only the host-only class names built on them.
 */

/** Joins conditional Tailwind class names without pulling in a runtime dependency. */
export function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

/** Shared card surface used by empty states and diagnostic rows. */
export const cardClass = "rounded-lg border border-line-soft bg-surface shadow-soft";

/** Shared background for secondary workspace navigation sidebars: transparent so the app gradient shows through, matching the chat role sidebar. */
export const secondarySidebarSurfaceClass = "bg-transparent";

/** Shared hover row: sidebar navigation entries and in-content expandable rows (memory timeline nodes). */
export const sidebarNavItemClass =
  "rounded-md transition-colors hover:bg-surface-hover focus-visible:bg-surface-hover";

/** Shared input styling for form controls outside the chat composer. */
export const inputClass =
  "w-full rounded-md border border-line bg-surface px-3.5 py-2.5 text-body text-ink transition placeholder:text-ink-faint hover:border-line-strong";

/** Shared compact field styling for editable values in a settings row (`SettingsField`). */
export const settingsInputClass = "w-full rounded-md border border-line bg-surface-soft px-2.5 py-2 text-body-sm text-ink transition placeholder:text-ink-faint hover:border-line-strong focus:bg-surface";

/** Vertical rhythm between the titled groups (`SettingsGroup`) of one settings page. */
export const settingsGroupStackClass = "grid gap-7";

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
 * Companion to the host's sidebar track motion for a sidebar's own content:
 * the content keeps its fixed width and only fades/slides, which never
 * relayouts. Under reduced motion the content only fades.
 */
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

/** Height, padding and type of a compact (36px) labeled button; compose it with a surface class. */
export const compactButtonSizeClass = "inline-flex h-9 shrink-0 items-center justify-center gap-1.5 px-3.5 text-body-sm font-medium";

/** Compact secondary action button (surface + compact size). */
export const compactGhostButtonClass = cx(ghostButtonSurfaceClass, compactButtonSizeClass);

/** Shared secondary action button styling. */
export const ghostButtonClass = cx(ghostButtonSurfaceClass, "px-[18px] py-3");

/** Square icon-only action button (back, reset, tools): the one corner treatment for this role is rounded-md. */
export const iconButtonClass = cx(
  pressableClass,
  "grid h-10 w-10 shrink-0 place-items-center rounded-md border border-line bg-surface text-ink-secondary hover:border-line-strong hover:bg-surface-hover disabled:cursor-default disabled:opacity-40",
);

/** Soft pill badge for statuses and tags. */
export const badgeClass =
  "inline-flex items-center gap-1 rounded-full bg-accent-soft px-2.5 py-0.5 text-caption text-accent-text";

/**
 * Borderless 28px icon-only button (dismiss, back, header toggles), for
 * places where iconButtonClass's bordered 40px tile would be too heavy.
 * Its icon is h-4 w-4. Public since runtime API 3.1.14 (#720), e.g. for the
 * actions of a compact list row; the SDK's capability settings button uses it too.
 */
export const compactIconButtonClass = cx(
  compactPressableClass,
  "grid h-7 w-7 shrink-0 place-items-center rounded-md text-ink-muted hover:bg-surface-hover hover:text-ink",
);

/**
 * The dimmed, blurred backdrop behind a modal dialog (Base UI `Dialog.Backdrop`),
 * fading with `motion-backdrop`. Host-only (`host-internal`); shared with the
 * SDK's capability settings dialog.
 */
export const dialogBackdropClass = "confirm-dialog-backdrop motion-backdrop fixed inset-0 z-50 bg-ink/30 backdrop-blur-sm";
