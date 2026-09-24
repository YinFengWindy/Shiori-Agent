import { CheckCircle, Info, Warning, WarningCircle, X, type Icon } from "@phosphor-icons/react";
import { useEffect, useState, useSyncExternalStore } from "react";
import { cx } from "../styles";
import {
  dismissFeedback,
  feedbackDurationMs,
  getFeedbackSnapshot,
  subscribeFeedback,
  type FeedbackToast,
  type FeedbackTone,
} from "./feedbackStore";

const toneIcon: Record<FeedbackTone, Icon> = {
  success: CheckCircle,
  info: Info,
  warning: Warning,
  error: WarningCircle,
};

/** Tinted badge behind each tone's icon; the toast body itself stays neutral glass. */
const toneBadgeClass: Record<FeedbackTone, string> = {
  success: "bg-success-soft text-success-text",
  info: "bg-lavender-soft text-lavender-text",
  warning: "bg-warning-soft text-warning-text",
  error: "bg-danger-soft text-danger-text",
};

function FeedbackToastItem({ toast }: { toast: FeedbackToast }) {
  const [paused, setPaused] = useState(false);
  const Glyph = toneIcon[toast.tone];

  // Restarting the full duration after a pause (rather than resuming the
  // remainder) is deliberate: whoever just hovered the message was reading it.
  useEffect(() => {
    if (paused) return undefined;
    const timer = window.setTimeout(() => dismissFeedback(toast.id), feedbackDurationMs[toast.tone]);
    return () => window.clearTimeout(timer);
  }, [paused, toast.id, toast.tone]);

  return (
    <div
      className="feedback-toast surface-glass-strong pointer-events-auto flex w-full items-start gap-2.5 rounded-lg py-2.5 pl-2.5 pr-2 text-body text-ink"
      role={toast.tone === "error" ? "alert" : "status"}
      data-tone={toast.tone}
      onPointerEnter={() => setPaused(true)}
      onPointerLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <span className={cx("grid h-6 w-6 shrink-0 place-items-center rounded-full", toneBadgeClass[toast.tone])} aria-hidden="true">
        <Glyph className="h-4 w-4" weight="bold" />
      </span>
      <span className="min-w-0 flex-1 break-words pt-0.5 leading-5">{toast.message}</span>
      {toast.action ? (
        <button
          type="button"
          className="shrink-0 rounded-md px-2 py-0.5 text-body-sm font-medium text-accent-text transition-colors hover:bg-accent-softer"
          onClick={() => {
            dismissFeedback(toast.id);
            toast.action?.onSelect();
          }}
        >
          {toast.action.label}
        </button>
      ) : null}
      <button
        type="button"
        className="grid h-6 w-6 shrink-0 place-items-center rounded-md text-ink-muted transition-colors hover:bg-surface-hover hover:text-ink"
        aria-label="关闭提示"
        onClick={() => dismissFeedback(toast.id)}
      >
        <X className="h-3.5 w-3.5" weight="bold" />
      </button>
    </div>
  );
}

/**
 * The single on-screen outlet for transient feedback (success / info /
 * warning / error). Mounted once at the app root so it is visible on every
 * view, including the onboarding flow and full-screen plugin pages; messages
 * are raised through `feedback.*` in `feedbackStore`. While a status banner
 * sits under the title bar (`--status-banner-offset`, set by
 * `BridgeOfflineBanner`) the stack starts below it instead of covering it.
 */
export function FeedbackToaster() {
  const toasts = useSyncExternalStore(subscribeFeedback, getFeedbackSnapshot, getFeedbackSnapshot);
  if (toasts.length === 0) return null;
  return (
    <div
      className="pointer-events-none fixed left-1/2 top-[calc(var(--titlebar-height)+14px+var(--status-banner-offset,0px))] z-[60] grid w-[min(26rem,calc(100vw-2rem))] -translate-x-1/2 gap-2"
      aria-live="polite"
    >
      {toasts.map((toast) => <FeedbackToastItem key={toast.id} toast={toast} />)}
    </div>
  );
}
