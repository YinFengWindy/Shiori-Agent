import { useCallback, useState } from "react";
import { errorMessage } from "@shiori/plugin-sdk";

/**
 * One user action (a save, a delete) run from a view: `busy` while it runs,
 * and its failure kept in `error` for the view to show (the view is the
 * boundary that reports it). `run` resolves to whether the action succeeded.
 */
export function useBusyAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = useCallback(async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await action();
      return true;
    } catch (failure) {
      setError(errorMessage(failure, { includeDetail: true }));
      return false;
    } finally {
      setBusy(false);
    }
  }, []);
  const clearError = useCallback(() => setError(""), []);
  return { busy, error, run, clearError };
}
