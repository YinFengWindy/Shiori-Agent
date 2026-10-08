import { useBatchPaging } from "../shared/batchPaging";
import type { DesktopInvoke } from "../shared/bridgeInvoke";
import { useScopedRead } from "../shared/useScopedRead";
import { readAffectionHistory } from "./affectionHistory";
import { appendAffectionBatch, firstAffectionBatch, type AffectionHistoryBatches } from "./affectionSelectors";

/**
 * A role's affection history with "load more" batches, read through the same
 * scoped-read and paging primitives as the memory timeline. Another role
 * restarts at the first batch.
 */
export function useAffectionHistory(invoke: DesktopInvoke, roleId: string) {
  const paging = useBatchPaging(roleId);
  const batches = useScopedRead<AffectionHistoryBatches>({
    scope: roleId,
    key: paging.key,
    read: async () => firstAffectionBatch(await readAffectionHistory(invoke, roleId, paging.page)),
    merge: appendAffectionBatch,
  });
  return {
    /** Every loaded entry plus the newest summary; null before the first response. */
    loaded: batches.value?.list ?? null,
    loading: batches.loading,
    error: batches.error,
    hasMore: Boolean(batches.value && !batches.value.exhausted),
    loadMore: paging.loadMore,
    /** Re-requests the batch that failed; earlier batches stay. */
    retry: paging.retry,
  };
}
