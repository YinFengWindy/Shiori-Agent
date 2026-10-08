import { useEffect, useState } from "react";
import { useBatchPaging } from "../shared/batchPaging";
import { useScopedRead } from "../shared/useScopedRead";
import { memoryReadKey, readSemanticBatch, type MemoryReadContext } from "./memoryReads";
import {
  initialSemanticQuery, sameSemanticFilters, sameSemanticQuery,
  type RoleSemanticFilters, type RoleSemanticQuery,
} from "./roleSemanticMemory";
import { appendTimelineBatch, firstTimelineBatch, type TimelineBatches } from "./timelineSelectors";

/**
 * The filters this role's engine last declared. They outlive the list of one
 * query, so the pickers stay put while the next query loads or fails.
 */
function useDeclaredFilters(roleId: string, batches: TimelineBatches | null) {
  const [declared, setDeclared] = useState<{ roleId: string; filters: RoleSemanticFilters | null }>({ roleId, filters: null });
  const list = batches?.list ?? null;
  useEffect(() => {
    if (!list) return;
    // A disabled engine offers nothing to filter on.
    const filters = list.status === "ready" ? list.filters : null;
    setDeclared((previous) => previous.roleId === roleId && sameSemanticFilters(previous.filters, filters) ? previous : { roleId, filters });
  }, [list, roleId]);
  return declared.roleId === roleId ? declared.filters : null;
}

/**
 * Timeline list state: the query, "load more" batches and expanded items.
 * Any change of client, role, refresh or query opens a new scope, which
 * restarts at the first batch and collapses every item.
 */
export function useMemoryTimeline(context: MemoryReadContext) {
  const [query, setQuery] = useState(initialSemanticQuery);
  const scope = memoryReadKey(context, JSON.stringify(query));
  const paging = useBatchPaging(scope);
  const [expanded, setExpanded] = useState<{ scope: string; ids: string[] }>({ scope, ids: [] });
  const expandedIds = expanded.scope === scope ? expanded.ids : [];

  const batches = useScopedRead<TimelineBatches>({
    scope,
    key: paging.key,
    read: async () => firstTimelineBatch(await readSemanticBatch(context, query, paging.page)),
    merge: appendTimelineBatch,
  });
  const filters = useDeclaredFilters(context.roleId, batches.value);

  return {
    query,
    /** Applies a query change; an identical query keeps the current state. */
    updateQuery: (patch: Partial<RoleSemanticQuery>) => setQuery((previous) => {
      const next = { ...previous, ...patch };
      return sameSemanticQuery(previous, next) ? previous : next;
    }),
    filters,
    list: batches.value?.list ?? null,
    loading: batches.loading,
    error: batches.error,
    hasMore: Boolean(batches.value && !batches.value.exhausted),
    loadMore: paging.loadMore,
    /** Re-requests the batch that failed; earlier batches stay. */
    retry: paging.retry,
    expandedIds,
    toggle: (id: string) => setExpanded({
      scope,
      ids: expandedIds.includes(id) ? expandedIds.filter((item) => item !== id) : [...expandedIds, id],
    }),
  };
}
