import { showFeedback, type FeedbackAction, type FeedbackTone } from "../shared/feedback/feedbackStore";
import { InlineError, type InlineErrorProps } from "../shared/feedback/InlineError";
import { feedbackTonePersona } from "../shared/mascot/mascotFeedback";

/*
 * 吟风 for plugin UIs (runtime API 2.4.0): the host's toast queue and inline
 * error block, reached through `PluginHostServices.feedback` and
 * `PluginHostServices.ui.InlineError`. A plugin opts in per call with
 * `persona: true` and only gets the host's tone-generic persona — it cannot
 * put words in her mouth. The 看板娘 switch (设置 › 外观) still wins: off,
 * everything renders plain.
 */

/** Options of a plugin toast. */
export type PluginFeedbackOptions = {
  /** Technical cause folded behind 「详情」. */
  detail?: string;
  /** One follow-up the user can take from the toast. */
  action?: FeedbackAction;
  /**
   * Let 吟风 front this toast with the host's rule for its tone: a line for
   * error / warning, only her face for success / info. Default false.
   */
  persona?: boolean;
};

/** A plugin's reporter into the host toast queue, one method per tone. */
export type PluginHostFeedback = Record<FeedbackTone, (message: string, options?: PluginFeedbackOptions) => void>;

const reporterFor = (tone: FeedbackTone) => (message: string, options: PluginFeedbackOptions = {}) => {
  showFeedback({ tone, message, action: options.action, detail: options.detail, persona: options.persona ? feedbackTonePersona[tone] : undefined });
};

/** The host implementation of `PluginHostServices.feedback`. */
export const pluginHostFeedback: PluginHostFeedback = {
  success: reporterFor("success"),
  info: reporterFor("info"),
  warning: reporterFor("warning"),
  error: reporterFor("error"),
};

/** Props of `PluginHostServices.ui.InlineError`: the host block, with a yes/no persona. */
export type HostInlineErrorProps = Omit<InlineErrorProps, "persona"> & {
  /** Let 吟风 front the block with the host's generic inline-error line. Default false. */
  persona?: boolean;
};

/** The host's in-page error block for plugin UIs (`PluginHostServices.ui.InlineError`). */
export function HostInlineError({ persona = false, ...props }: HostInlineErrorProps) {
  return <InlineError {...props} persona={persona ? "generic" : false} />;
}
