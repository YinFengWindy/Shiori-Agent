/** Visual and semantic weight of one transient feedback message. */
export type FeedbackTone = "success" | "info" | "warning" | "error";

/** One optional follow-up the user can take straight from the message. */
export type FeedbackAction = {
  label: string;
  onSelect: () => void;
};

/** A queued feedback message as rendered by `FeedbackToaster`. */
export type FeedbackToast = {
  id: number;
  tone: FeedbackTone;
  message: string;
  action?: FeedbackAction;
};

/** Options shared by every `feedback.*` reporter call. */
export type FeedbackOptions = {
  action?: FeedbackAction;
};

/** The injectable reporter hooks receive instead of owning their own message state. */
export type FeedbackReporter = Record<FeedbackTone, (message: string, options?: FeedbackOptions) => void>;

type Listener = () => void;

/** Oldest messages are dropped beyond this so a burst never buries the view. */
export const maxVisibleFeedback = 3;

/**
 * How long each tone stays up before dismissing itself. Errors stay longest
 * because they usually ask the user to do something; every toast can also be
 * closed by hand, and hovering or focusing one pauses its timer.
 */
export const feedbackDurationMs: Record<FeedbackTone, number> = {
  success: 2400,
  info: 3200,
  warning: 5000,
  error: 8000,
};

// Module-level singleton, same shape as `pluginEnabledStateStore`: feedback
// is raised from hooks, settings sections, plugin surfaces and leaf menus
// that share no mounted ancestor close enough for prop threading, while the
// one toaster that renders it sits at the app root.
let toasts: readonly FeedbackToast[] = [];
let nextId = 1;
const listeners = new Set<Listener>();

function publish(next: readonly FeedbackToast[]): void {
  toasts = next;
  for (const listener of listeners) listener();
}

/**
 * Queues one message. An identical tone + message already on screen is moved
 * to the end with a fresh id instead of stacking a duplicate, which restarts
 * its timer — repeated failures of the same request read as one message.
 * Returns the queued id, or 0 when the message was empty.
 */
export function showFeedback(input: { tone: FeedbackTone; message: string; action?: FeedbackAction }): number {
  const message = input.message.trim();
  if (!message) return 0;
  const toast: FeedbackToast = { id: nextId++, tone: input.tone, message, action: input.action };
  const remaining = toasts.filter((item) => item.tone !== toast.tone || item.message !== toast.message);
  publish([...remaining, toast].slice(-maxVisibleFeedback));
  return toast.id;
}

/** Removes one message; unknown ids are ignored so late timers are harmless. */
export function dismissFeedback(id: number): void {
  if (!toasts.some((item) => item.id === id)) return;
  publish(toasts.filter((item) => item.id !== id));
}

/** Current queue, oldest first. Stable reference between changes (a `useSyncExternalStore` snapshot). */
export function getFeedbackSnapshot(): readonly FeedbackToast[] {
  return toasts;
}

/** Subscribes to queue changes; returns the unsubscribe function. */
export function subscribeFeedback(listener: Listener): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** Clears the queue; tests use it to isolate cases sharing this module. */
export function resetFeedback(): void {
  publish([]);
}

function reporterFor(tone: FeedbackTone) {
  return (message: string, options?: FeedbackOptions) => { showFeedback({ tone, message, action: options?.action }); };
}

/** The app-wide reporter bound to this store. */
export const feedback: FeedbackReporter = {
  success: reporterFor("success"),
  info: reporterFor("info"),
  warning: reporterFor("warning"),
  error: reporterFor("error"),
};

/** Normalizes a thrown value into the message the error toast shows. */
export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
