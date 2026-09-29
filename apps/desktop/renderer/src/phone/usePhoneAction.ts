import { useCallback, useState } from "react";
import { errorMessage } from "../shared/feedback/feedbackStore";

/** What `usePhoneAction`'s `run` resolves to when the action threw. */
export const actionFailed: unique symbol = Symbol("actionFailed");

/**
 * Runs one user action at a time (a save, a delete) for a phone screen:
 * `busy` while it runs, and its failure kept in `error` for the screen to
 * show (the screen is the boundary that reports it). `run` resolves to the
 * action's result, or `actionFailed` when it threw.
 */
export function usePhoneAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = useCallback(async <T,>(action: () => Promise<T>): Promise<T | typeof actionFailed> => {
    setBusy(true);
    setError("");
    try {
      return await action();
    } catch (failure) {
      setError(errorMessage(failure));
      return actionFailed;
    } finally {
      setBusy(false);
    }
  }, []);
  const clearError = useCallback(() => setError(""), []);
  return { busy, error, run, clearError };
}
