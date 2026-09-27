import { useState } from "react";
import { memoryClientKey, readSemanticBatch, type MemoryRpc } from "./memoryReads";
import { appendSemanticBatch } from "./timelineSelectors";
import { initialSemanticQuery, sameSemanticQuery, type RoleSemanticList, type RoleSemanticQuery } from "./roleSemanticMemory";
import { useMemoryRead } from "./useMemoryRead";

/**
 * Timeline list state: the query, "load more" batches and expanded items.
 * Any change of client, role, refresh or query opens a new scope, which
 * restarts at the first batch and collapses every item.
 */
export function useMemoryTimeline(client: MemoryRpc, roleId: string, refreshKey: number) {
  const [query, setQuery] = useState(initialSemanticQuery);
  const scope = `${memoryClientKey(client)}:${roleId}:${refreshKey}:${JSON.stringify(query)}`;
  const [paging, setPaging] = useState({ scope, page: 1 });
  const [expanded, setExpanded] = useState<{ scope: string; ids: string[] }>({ scope, ids: [] });
  const page = paging.scope === scope ? paging.page : 1;
  const expandedIds = expanded.scope === scope ? expanded.ids : [];

  const list = useMemoryRead<RoleSemanticList>({
    scope,
    key: `${scope}#${page}`,
    read: () => readSemanticBatch(client, roleId, query, page),
    merge: appendSemanticBatch,
  });
  // The last declaration survives reloads of this role, so pickers stay put while a new query loads.
  const declared = list.last?.role_id === roleId && list.last.status === "ready" ? list.last.filters : null;

  return {
    query,
    /** Applies a query change; an identical query keeps the current state. */
    updateQuery: (patch: Partial<RoleSemanticQuery>) => setQuery((previous) => {
      const next = { ...previous, ...patch };
      return sameSemanticQuery(previous, next) ? previous : next;
    }),
    filters: declared,
    list: list.value,
    loading: list.loading,
    error: list.error,
    loadMore: () => setPaging({ scope, page: page + 1 }),
    expandedIds,
    toggle: (id: string) => setExpanded({
      scope,
      ids: expandedIds.includes(id) ? expandedIds.filter((item) => item !== id) : [...expandedIds, id],
    }),
  };
}
