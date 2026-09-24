import { compactPressableClass, cx, pressableClass } from "../shared/styles";

/** Underline-style identity field (name/intro) shared by detail and create pages; opts out of the global focus halo. */
export const roleIdentityInputClass =
  "w-full border-0 border-b border-transparent bg-transparent px-0 py-1 transition hover:border-line focus:border-accent focus:shadow-none focus:outline-none";

/** Unified input/select surface for the role editor tabs, capability cards and create page. */
export const roleFieldClass =
  "w-full rounded-md border border-transparent bg-surface-soft px-3.5 py-2.5 text-body text-ink transition placeholder:text-ink-faint hover:bg-surface-hover focus:bg-surface";

/** Field label wrapper with the shared caption color. */
export const roleFieldLabelClass = "grid gap-1.5 text-caption text-ink-muted";

/** Section heading used at the top of each role editor group. */
export const roleSectionTitleClass = "m-0 text-title-sm text-ink";

/** Small keyword chip used by knowledge entries. */
export const roleChipClass =
  "inline-flex max-w-full items-center truncate rounded-full bg-surface-soft px-2.5 py-1 text-caption leading-4 text-ink-secondary";

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
