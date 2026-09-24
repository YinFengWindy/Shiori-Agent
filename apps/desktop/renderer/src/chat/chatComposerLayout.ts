/** Line height of the composer textarea (Tailwind `leading-6`). */
export const chatComposerLineHeightPx = 24;

/** The textarea never grows past this many lines; longer drafts scroll inside it. */
export const chatComposerMaxLines = 10;

/** Share of the chat pane the textarea may take before it scrolls. */
const textareaPaneShare = 0.4;

/** Share of the chat pane the pending-attachment strip may take before it scrolls. */
const attachmentsPaneShare = 0.22;

/** Tallest the attachment strip gets: two rows of 56px previews with their gap. */
const attachmentsMaxHeightPx = 128;

/** The composer floats this far above the pane bottom (Tailwind `bottom-10`). */
export const chatComposerBottomOffsetPx = 40;

/** Room kept between the composer's top and the pane's top edge (below the chat header). */
const composerTopClearancePx = 16;

export type ChatComposerLimits = {
  textareaMaxHeight: number;
  attachmentsMaxHeight: number;
  /** Cap on the whole composer card so it can never climb under the header. */
  composerMaxHeight: number;
};

/**
 * Sizes the composer against the chat pane it floats in: the textarea stops
 * at ~40% of the pane or 10 lines, the attachment strip at two rows, and the
 * card as a whole always leaves the top of the pane free. `paneHeight` 0
 * means "not measured yet" and yields the line-count caps alone.
 */
export function getChatComposerLimits(paneHeight: number): ChatComposerLimits {
  const lineCap = chatComposerLineHeightPx * chatComposerMaxLines;
  if (paneHeight <= 0) {
    return { textareaMaxHeight: lineCap, attachmentsMaxHeight: attachmentsMaxHeightPx, composerMaxHeight: Number.POSITIVE_INFINITY };
  }
  const minTextarea = chatComposerLineHeightPx * 2;
  return {
    textareaMaxHeight: Math.max(minTextarea, Math.min(Math.floor(paneHeight * textareaPaneShare), lineCap)),
    attachmentsMaxHeight: Math.max(56, Math.min(Math.floor(paneHeight * attachmentsPaneShare), attachmentsMaxHeightPx)),
    composerMaxHeight: Math.max(minTextarea, paneHeight - chatComposerBottomOffsetPx - composerTopClearancePx),
  };
}
