import type { FeedbackTone, PluginFeedbackOptions, PluginHostFeedback, PluginPersona } from "@shiori/plugin-sdk";
import { showFeedback } from "../shared/feedback/feedbackStore";
import { feedbackTonePersona } from "../shared/mascot/mascotFeedback";

/** The plugin feedback contract is owned by `@shiori/plugin-sdk` (#440); re-exported for host callers. */
export type { PluginFeedbackOptions, PluginHostFeedback, PluginPersona };

/*
 * 吟风 for plugin UIs (runtime API 2.4.0). A plugin opts in per call with
 * `persona`: `true` / `"generic"` for the surface's generic line, or a scene
 * key (`personaSceneLines`: not_configured, unauthorized, quota, network,
 * upstream, destructive, discard, confirm) for the host's line for that
 * scene. The words are always the host's — a plugin picks a scene, never a
 * sentence. The 看板娘 switch (设置 › 外观) still wins: off, everything
 * renders plain.
 */

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
