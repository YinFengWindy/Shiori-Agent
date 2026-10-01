import { describeStoryFailure } from "./storyFailure";
import { useCallback, useState } from "react";

export type RunStoryOperation = <T>(
  operation: () => Promise<T>,
  apply: (value: T) => Promise<void> | void,
) => Promise<void>;

/** Owns shared busy and surfaced-error state for Story bridge operations. */
export function useStoryPresentationOperation() {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ReturnType<typeof describeStoryFailure> | null>(null);
  const clearError = useCallback(() => setFailure(null), []);
  const reportError = useCallback((cause: unknown, summary?: string) => setFailure(describeStoryFailure(cause, summary)), []);

  const run = useCallback<RunStoryOperation>(async (operation, apply) => {
    setBusy(true);
    setFailure(null);
    try {
      const result = await operation();
      await apply(result);
    } catch (operationError) {
      reportError(operationError);
    } finally {
      setBusy(false);
    }
  }, [reportError]);

  return {
    busy,
    error: failure?.error ?? "",
    ...(failure?.errorDetail ? { errorDetail: failure.errorDetail } : {}),
    clearError,
    reportError,
    run,
  };
}
