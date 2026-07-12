/** Joins conditional Tailwind class names without pulling in a runtime dependency. */
export function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

/** Shared card surface used by empty states and diagnostic rows. */
export const cardClass = "rounded-[18px] border border-stroke bg-panel";

/** Shared small-body text class for non-titlebar desktop content. */
export const bodyTextClass = "text-xs leading-5";

/** Shared input styling for form controls outside the chat composer. */
export const inputClass =
  "w-full rounded-md border border-[#D8DCE2] !bg-[#F3F5F7] px-3.5 py-3 text-text transition focus:border-[#D8DCE2] focus:outline-none focus:ring-2 focus:ring-gray-300/70 focus-visible:border-[#D8DCE2] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-300/70";

/** Shared textarea styling for role prompt fields. */
export const textareaClass = cx(inputClass, "min-h-24 resize-y");

/** Shared primary action button styling. */
export const primaryButtonClass =
  "cursor-pointer rounded-md border border-transparent bg-gradient-to-br from-primary to-[#e07b4d] px-[18px] py-3 text-white disabled:cursor-default disabled:opacity-50";

/** Shared secondary action button styling. */
export const ghostButtonClass =
  "cursor-pointer rounded-md border border-stroke bg-[#F3F5F7] px-[18px] py-3 text-text disabled:cursor-default disabled:opacity-50";

/** Shared keyboard-only focus ring for key desktop actions. */
export const focusVisibleRingClass =
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-300/70";

/** Shared keyboard-only focus ring for key actions shown on dark or image surfaces. */
export const focusVisibleWhiteRingClass =
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-white/20";

/** Shared keyboard-only focus ring for destructive confirmations. */
export const focusVisibleDangerRingClass =
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(143,43,24,0.16)]";

/** Reusable panel header layout. */
export const panelHeadClass = "panel-head mb-3 flex items-center justify-between";

/** Reusable serif panel title. */
export const panelTitleClass = "m-0 font-serif text-lg font-semibold";
