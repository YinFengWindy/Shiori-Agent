import type { FeedbackOptions, FeedbackReporter, FeedbackTone } from "../feedback/feedbackStore";

/** One reporter call captured by `createFeedbackRecorder`. */
export type RecordedFeedback = { tone: FeedbackTone; message: string; options?: FeedbackOptions };

/** A `FeedbackReporter` that records calls instead of queueing toasts, for hook and workflow tests. */
export function createFeedbackRecorder() {
  const entries: RecordedFeedback[] = [];
  const record = (tone: FeedbackTone) => (message: string, options?: FeedbackOptions) => {
    entries.push({ tone, message, options });
  };
  const reporter: FeedbackReporter = {
    success: record("success"),
    info: record("info"),
    warning: record("warning"),
    error: record("error"),
  };
  return {
    reporter,
    entries,
    get last() { return entries.at(-1) ?? null; },
    messages(tone: FeedbackTone) { return entries.filter((entry) => entry.tone === tone).map((entry) => entry.message); },
  };
}
