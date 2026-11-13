import { cx, inputClass } from "@yinfengwindy/shiori-sdk";

/*
 * Story-owned class names. Colors come from the `--story-*` tokens in
 * story.css; focus rings come from the host's global `:focus-visible` rule.
 */

/** Horizontal padding shared by every Story paper surface. */
export const storyGutterClass = "px-[clamp(18px,4vw,40px)]";

/** Header row of a Story paper surface: back button plus the page title. */
export const storyPageHeaderClass = cx("flex items-center gap-4 border-b border-[color:var(--story-line)] py-5", storyGutterClass);

/** Page title on a Story paper surface. */
export const storyPageTitleClass = "m-0 font-serif text-2xl font-semibold text-[color:var(--story-wine)]";

/** Section heading inside a Story paper surface. */
export const storySectionTitleClass = "m-0 font-serif text-xl font-semibold text-[color:var(--story-wine)]";

/** Square icon button on Story paper. */
export const storyIconButtonClass = "grid h-9 w-9 shrink-0 place-items-center rounded-md text-[color:var(--story-rose)] transition-colors hover:bg-[color:var(--story-paper-strong)] hover:text-[color:var(--story-wine)] disabled:cursor-default disabled:opacity-40";

/** Text button with an icon, used for the primary step of a Story form. */
export const storyPrimaryButtonClass = "inline-flex h-10 shrink-0 items-center gap-2 rounded-md bg-[color:var(--story-wine)] px-4 text-sm font-semibold text-[color:var(--story-on-wine)] shadow-[var(--story-shadow-selected)] transition-colors hover:bg-[color:var(--story-wine-hover)] disabled:cursor-default disabled:opacity-45";

/** Quiet text button with an icon on Story paper. */
export const storySecondaryButtonClass = "inline-flex h-10 shrink-0 items-center gap-2 rounded-md px-3 text-sm text-[color:var(--story-wine)] transition-colors hover:bg-[color:var(--story-paper-strong)] disabled:cursor-default disabled:opacity-45";

/** Destructive text button on Story paper. */
export const storyDangerButtonClass = "inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md px-2.5 text-sm text-[color:var(--story-danger)] transition-colors hover:bg-[color:var(--story-paper-strong)] disabled:cursor-default disabled:opacity-45";

/** Text field on Story paper, built on the SDK field so focus styling stays the host's. */
export const storyInputClass = cx(inputClass, "border-[color:var(--story-line-field)] !bg-[color:var(--story-paper-field)] text-[color:var(--story-ink)]");

/** Field label stacked above its control. */
export const storyFieldLabelClass = "grid gap-1.5 text-xs text-[color:var(--story-ink-muted)]";

/** Muted supporting copy on Story paper. */
export const storyMutedTextClass = "text-[color:var(--story-ink-muted)]";

/** Empty or status line on Story paper. */
export const storyEmptyTextClass = "m-0 border-b border-[color:var(--story-line)] py-5 text-sm text-[color:var(--story-ink-muted)]";

/** Option group track that holds one selected Story choice. */
export const storySegmentTrackClass = "grid overflow-hidden rounded-md border border-[color:var(--story-line-field)] bg-[color:var(--story-paper)] p-1";

/** One option inside a Story option group. */
export function storySegmentOptionClass(selected: boolean) {
  return selected
    ? "min-h-9 rounded-[3px] bg-[color:var(--story-wine)] px-3 py-1.5 text-xs font-semibold text-[color:var(--story-on-wine)] shadow-[var(--story-shadow-selected)] transition-colors"
    : "min-h-9 rounded-[3px] px-3 py-1.5 text-xs font-medium text-[color:var(--story-wine)] transition-colors hover:bg-[color:var(--story-paper-strong)]";
}

/** Round control on the dark game stage. */
export const storyStageControlClass = "story-game-control story-game-readable grid h-10 w-10 place-items-center rounded-md text-[color:var(--story-stage-ink-muted)] transition-colors hover:bg-[color:var(--story-stage-glass-hover)] hover:text-[color:var(--story-stage-ink)] disabled:cursor-not-allowed disabled:opacity-45";
