import { showFeedback, type FeedbackAction, type FeedbackTone } from "../shared/feedback/feedbackStore";
import { feedbackTonePersona } from "../shared/mascot/mascotFeedback";
import type { PersonaSceneKey } from "../shared/mascot/mascotLines";

/*
 * 吟风 for plugin UIs (runtime API 2.4.0). A plugin opts in per call with
 * `persona`: `true` / `"generic"` for the surface's generic line, or a scene
 * key (`personaSceneLines`: not_configured, unauthorized, quota, network,
 * upstream, destructive, discard, confirm) for the host's line for that
 * scene. The words are always the host's — a plugin picks a scene, never a
 * sentence. The 看板娘 switch (设置 › 外观) still wins: off, everything
 * renders plain.
 */

/** How a plugin asks for 吟风: not at all (`false`, the default), generically, or by scene. */
export type PluginPersona = boolean | "generic" | PersonaSceneKey;

/** Options of a plugin toast. */
export type PluginFeedbackOptions = {
  /** Technical cause folded behind 「详情」. */
  detail?: string;
  /** One follow-up the user can take from the toast. */
  action?: FeedbackAction;
  /**
   * Let 吟风 front this toast. `true` / `"generic"` follow the host's rule
   * for the tone (a line for error / warning, only her face for success /
   * info); a scene key uses that scene's line. Default false.
   */
  persona?: PluginPersona;
  /**
   * With `persona`: show only her face (with the persona's expression), not
   * her line — for when the plugin already shows the same line on screen
   * (e.g. a failure card fronted by the same scene). Default false.
   */
  personaQuiet?: boolean;
};

/** A plugin's reporter into the host toast queue, one method per tone. */
export type PluginHostFeedback = Record<FeedbackTone, (message: string, options?: PluginFeedbackOptions) => void>;

/** The toast persona a plugin's request resolves to for `tone`, or undefined for a plain toast. */
function toastPersona(tone: FeedbackTone, persona: PluginPersona | undefined) {
  if (!persona) return undefined;
  return persona === true || persona === "generic" ? feedbackTonePersona[tone] : persona;
}

const reporterFor = (tone: FeedbackTone) => (message: string, options: PluginFeedbackOptions = {}) => {
  showFeedback({ tone, message, action: options.action, detail: options.detail, persona: toastPersona(tone, options.persona), personaQuiet: options.personaQuiet });
};

/** The host implementation of `PluginHostServices.feedback`. */
export const pluginHostFeedback: PluginHostFeedback = {
  success: reporterFor("success"),
  info: reporterFor("info"),
  warning: reporterFor("warning"),
  error: reporterFor("error"),
};
