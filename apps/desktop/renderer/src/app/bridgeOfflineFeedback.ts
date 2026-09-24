import { useLayoutEffect } from "react";
import { useLatestRef } from "../shared/useLatestRef";
import { dismissFeedbackWhere, setFeedbackFilter, type FeedbackFilter } from "../shared/feedback/feedbackStore";

// The main process reports a bridge that went away with these raw English
// reasons (see apps/desktop/src/bridge/bridgeClient.ts); every request made
// meanwhile fails with one of them.
const bridgeStoppedPattern = /bridge stopped/gi;
const bridgeExitedPattern = /bridge exited(?: with code (-?\d+|null))?/gi;

/**
 * Whether a message only restates that the local bridge is down: it carries
 * one of the bridge-exit reasons, or the exact reason the banner is showing.
 */
export function isBridgeUnavailableMessage(message: string, bridgeError: string): boolean {
  const reason = bridgeError.split("\n", 1)[0]?.trim() ?? "";
  return new RegExp(bridgeStoppedPattern.source, "i").test(message)
    || new RegExp(bridgeExitedPattern.source, "i").test(message)
    || (reason.length > 0 && message.includes(reason));
}

/** Replaces the raw English bridge-exit reasons inside a message with Chinese. */
export function localizeBridgeMessage(message: string): string {
  return message
    .replace(bridgeStoppedPattern, "本地服务已停止")
    .replace(bridgeExitedPattern, (_match, code?: string) => (code ? `本地服务已退出（代码 ${code}）` : "本地服务已退出"));
}

/**
 * The feedback filter the offline banner installs: while the banner is up,
 * errors and warnings that only say "the bridge is down" are dropped (the
 * banner already says it and offers the restart); everything else — and any
 * bridge message arriving while the banner is not up — passes, with the raw
 * English reason translated.
 */
export function createBridgeFeedbackFilter(state: () => { bannerVisible: boolean; bridgeError: string }): FeedbackFilter {
  return (input) => {
    if (input.tone !== "error" && input.tone !== "warning") return input;
    const { bannerVisible, bridgeError } = state();
    if (bannerVisible && isBridgeUnavailableMessage(input.message, bridgeError)) return null;
    const message = localizeBridgeMessage(input.message);
    return message === input.message ? input : { ...input, message };
  };
}

/**
 * Keeps bridge-down noise out of the toast stack for as long as the offline
 * banner is mounted, and clears such toasts already queued when the banner
 * appears (a failed request can report before the bridge-exit event lands).
 */
export function useBridgeOfflineFeedbackFilter(bannerVisible: boolean, bridgeError: string): void {
  const latest = useLatestRef({ bannerVisible, bridgeError });
  useLayoutEffect(() => setFeedbackFilter(createBridgeFeedbackFilter(() => latest.current)), [latest]);
  useLayoutEffect(() => {
    if (!bannerVisible) return;
    dismissFeedbackWhere((toast) => (toast.tone === "error" || toast.tone === "warning")
      && (isBridgeUnavailableMessage(toast.message, bridgeError) || /本地服务已(停止|退出)/.test(toast.message)));
  }, [bannerVisible, bridgeError]);
}
