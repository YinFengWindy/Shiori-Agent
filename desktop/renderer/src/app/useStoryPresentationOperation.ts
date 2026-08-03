import { useCallback, useState } from "react";

export type RunStoryOperation = <T>(
  operation: () => Promise<T>,
  apply: (value: T) => Promise<void> | void,
) => Promise<void>;

/** Owns shared busy and surfaced-error state for Story bridge operations. */
export function useStoryPresentationOperation() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const clearError = useCallback(() => setError(""), []);

  const run = useCallback<RunStoryOperation>(async (operation, apply) => {
    setBusy(true);
    setError("");
    try {
      const result = await operation();
      await apply(result);
    } catch (operationError) {
      setError(operationError instanceof Error ? operationError.message : "剧情暂时无法响应");
    } finally {
      setBusy(false);
    }
  }, []);

  return {
    busy,
    error,
    clearError,
    reportError: setError,
    run,
  };
}
