import { useEffect, useState } from "react";
import { errorMessage, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { readAffectionHistory } from "./affectionHistory";
import { appendAffectionBatch, firstAffectionBatch, type AffectionHistoryBatches } from "./affectionSelectors";

/**
 * A role's affection history with "load more" batches. The panel is keyed by
 * role, so one hook instance serves one role and starts at the first batch.
 */
export function useAffectionHistory(client: PluginRpcClient, roleId: string) {
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [batches, setBatches] = useState<AffectionHistoryBatches | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    readAffectionHistory(client, roleId, page).then((result) => {
      if (cancelled) return;
      const batch = firstAffectionBatch(result);
      setBatches((previous) => (page === 1 || previous === null ? batch : appendAffectionBatch(previous, batch)));
      setLoading(false);
    }, (cause: unknown) => {
      if (cancelled) return;
      setError(errorMessage(cause));
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [attempt, client, page, roleId]);

  return {
    /** Every loaded entry plus the newest summary; null before the first response. */
    loaded: batches?.list ?? null,
    loading,
    error,
    hasMore: Boolean(batches && !batches.exhausted),
    loadMore: () => setPage((current) => current + 1),
    /** Re-requests the batch that failed; earlier batches stay. */
    retry: () => setAttempt((current) => current + 1),
  };
}
