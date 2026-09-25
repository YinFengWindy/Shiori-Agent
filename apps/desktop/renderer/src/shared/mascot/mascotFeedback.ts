import { createFeedbackReporter, type FeedbackOptions, type FeedbackToast, type FeedbackTone } from "../feedback/feedbackStore";
import { feedbackPersonaLines, type FeedbackPersona, type MascotCue } from "./mascotLines";

/**
 * The persona each tone gets when nobody asks for a specific one: errors
 * and warnings carry a line, success and info only her face (the rule is
 * spelled out on `feedbackPersonaLines`).
 */
export const feedbackTonePersona: Record<FeedbackTone, FeedbackPersona> = {
  success: "success",
  info: "info",
  warning: "warning",
  error: "generic",
};

const toneDefaults: Record<FeedbackTone, FeedbackOptions> = {
  success: { persona: feedbackTonePersona.success },
  info: { persona: feedbackTonePersona.info },
  warning: { persona: feedbackTonePersona.warning },
  error: { persona: feedbackTonePersona.error },
};

/**
 * The host's feedback reporter: the same store and toaster as `feedback`,
 * but every tone defaults to 吟风's persona for it (`feedbackTonePersona`),
 * so she fronts every host toast whenever the 看板娘 is on; a call can pass
 * a more specific persona. Plugin UIs report through their injected host
 * services (`PluginHostServices.feedback`), where she only appears when the
 * plugin opts in with `persona: true`.
 */
export const mascotFeedback = createFeedbackReporter(toneDefaults);

/**
 * What 吟风 shows on a toast: its persona's cue, or null for a plain toast.
 * The generic error line promises a 「详情」, so without a cause it falls
 * back to the brief one.
 */
export function feedbackPersonaCue(toast: Pick<FeedbackToast, "persona" | "detail">): MascotCue | null {
  if (!toast.persona) return null;
  if (toast.persona === "generic" && !toast.detail) return feedbackPersonaLines.genericBrief;
  return feedbackPersonaLines[toast.persona];
}
