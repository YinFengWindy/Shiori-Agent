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
  "w-full rounded-md border border-[#D8DCE2] bg-[rgba(255,252,246,0.95)] px-3.5 py-3 text-text transition focus:border-[#D8DCE2] focus:outline-none focus:ring-0 focus-visible:border-[#D8DCE2] focus-visible:outline-none focus-visible:ring-0";

/** Shared textarea styling for role prompt fields. */
export const textareaClass = cx(inputClass, "min-h-24 resize-y");

/** Shared primary action button styling. */
export const primaryButtonClass =
  "cursor-pointer rounded-full border border-transparent bg-gradient-to-br from-primary to-[#e07b4d] px-[18px] py-3 text-white disabled:cursor-default disabled:opacity-50";

/** Shared secondary action button styling. */
export const ghostButtonClass =
  "cursor-pointer rounded-full border border-stroke bg-[rgba(255,248,239,0.88)] px-[18px] py-3 text-text disabled:cursor-default disabled:opacity-50";

/** Reusable panel header layout. */
export const panelHeadClass = "panel-head mb-3 flex items-center justify-between";

/** Reusable serif panel title. */
export const panelTitleClass = "m-0 font-serif text-lg font-semibold";
