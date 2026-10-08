import { useState } from "react";
import { useMemoryRead } from "../memory/useMemoryRead";
import { readAffectionHistory } from "./affectionHistory";
import { appendAffectionBatch, firstAffectionBatch, type AffectionHistoryBatches } from "./affectionSelectors";

/**
 * A role's affection history with "load more" batches, read through the same
 * stale-dropping primitive as the memory timeline. Another role restarts at
 * the first batch.
 */
export function useAffectionHistory(roleId: string) {
  // `attempt` gives a retried batch a new read key for the same page.
  const [paging, setPaging] = useState({ roleId, page: 1, attempt: 0 });
  const { page, attempt } = paging.roleId === roleId ? paging : { page: 1, attempt: 0 };
  const batches = useMemoryRead<AffectionHistoryBatches>({
    scope: roleId,
    key: `${roleId}#${page}:${attempt}`,
    read: async () => firstAffectionBatch(await readAffectionHistory(window.miraDesktop.invoke, roleId, page)),
    merge: appendAffectionBatch,
  });
  return {
    history: batches.value?.page ?? null,
    loading: batches.loading,
    error: batches.error,
    hasMore: Boolean(batches.value && !batches.value.exhausted),
    loadMore: () => setPaging({ roleId, page: page + 1, attempt: 0 }),
    /** Re-requests the batch that failed; earlier batches stay. */
    retry: () => setPaging({ roleId, page, attempt: attempt + 1 }),
  };
}
