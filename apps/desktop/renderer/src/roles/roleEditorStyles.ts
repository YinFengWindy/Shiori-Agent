import { compactPressableClass, cx, pressableClass } from "@yinfengwindy/shiori-sdk";

/** Underline-style identity field (name/intro) shared by detail and create pages; opts out of the global focus halo. */
export const roleIdentityInputClass =
  "w-full border-0 border-b border-transparent bg-transparent px-0 py-1 transition hover:border-line focus:border-accent focus:shadow-none focus:outline-none";

/** Shared identity card for creating and editing a role. */
export const roleIdentityCardClass = "surface-glass relative isolate overflow-hidden rounded-xl";
/** Responsive avatar and identity field columns. */
export const roleIdentityLayoutClass = "grid items-center gap-6 sm:grid-cols-[auto_minmax(0,1fr)]";
/** Avatar geometry and surface shared by the picker and saved-role header. */
export const roleAvatarClass = "group grid h-28 w-28 shrink-0 place-items-center overflow-hidden rounded-full border-4 border-surface bg-gradient-accent-soft shadow-panel";
/** Editable role name with the same display typography in both editors. */
export const roleNameInputClass = cx(roleIdentityInputClass, "min-w-[6em] max-w-full font-display text-headline text-ink [field-sizing:content] placeholder:text-ink-faint");
/** Editable intro below the role name. */
export const roleDescriptionInputClass = cx(roleIdentityInputClass, "min-w-[8em] max-w-full text-body text-ink-secondary [field-sizing:content] placeholder:text-ink-faint");
/** Decorative identity background when no character portrait is available. */
export const roleIdentityBackdropClass = "pointer-events-none absolute inset-y-0 right-0 -z-10 w-1/2 bg-gradient-accent-soft [mask-image:linear-gradient(to_left,rgb(0_0_0)_20%,transparent)]";

/** The sticky action bar below a role's identity card. */
export const roleEditorToolbarClass = "sticky top-0 z-20 -mx-5 mb-7 mt-5 flex min-h-14 items-stretch gap-4 border-b border-line-soft bg-[var(--color-bg-glass)] px-5 backdrop-blur-md sm:-mx-8 sm:px-8";

const roleControlClass = "w-full rounded-md border px-3.5 py-2.5 text-body text-ink transition placeholder:text-ink-faint";

/** Unified input/select surface for the role editor tabs, capability cards and create page. */
export const roleFieldClass = cx(roleControlClass, "border-transparent bg-surface-soft hover:bg-surface-hover focus:bg-surface");

/** White profile editor; only unfocused fields hide the border so the global focus border remains visible. */
export const roleTextareaClass = cx(roleControlClass, "bg-surface [&:not(:focus)]:border-transparent enabled:hover:border-line-accent");

/** Field label wrapper with the shared caption color. */
export const roleFieldLabelClass = "grid gap-1.5 text-caption text-ink-muted";

/** Section heading used at the top of each role editor group. */
export const roleSectionTitleClass = "m-0 text-title-sm text-ink";

/** Compact quiet action rendered beside section headings (添加, 编辑参数). */
export const rolePanelGhostButtonClass = cx(
  pressableClass,
  "inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md px-2.5 text-body-sm font-medium text-ink-secondary hover:bg-surface-hover hover:text-ink disabled:cursor-not-allowed disabled:text-ink-faint",
);

/** Square 32px icon action for ordered rows (move up / down, remove). */
export const roleRowIconButtonClass = cx(
  compactPressableClass,
  "grid h-8 w-8 place-items-center rounded-md text-ink-muted hover:bg-surface-hover hover:text-ink disabled:cursor-not-allowed disabled:text-ink-faint",
);
