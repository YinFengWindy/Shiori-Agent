import { useState } from "react";

/** One page of a 1-based, offset-paged list: its items, the list total and the requested size. */
export type BatchPage<Item> = { items: Item[]; total: number; page_size: number };

/** The loaded list: every batch so far, and whether asking for another is pointless. */
export type LoadedBatches<List> = { list: List; exhausted: boolean };

/**
 * The end is reached when a batch comes back short, adds nothing new, or the
 * loaded items cover the total. Offset paging can still skip or repeat items
 * when the list changes between batches; that is an accepted limitation
 * (repeats are dropped by key, a new scope starts over).
 */
function loadedBatches<List extends BatchPage<unknown>>(list: List, returned: number, fresh: number): LoadedBatches<List> {
  const exhausted = fresh === 0 || returned < list.page_size || list.items.length >= list.total;
  return { list, exhausted };
}

/** The first batch of a scope. */
export function firstBatch<List extends BatchPage<unknown>>(list: List) {
  return loadedBatches(list, list.items.length, list.items.length);
}

/** Appends the next batch, dropping items an earlier batch already showed (by `keyOf`). */
export function appendBatch<List extends BatchPage<unknown>>(
  previous: LoadedBatches<List>,
  next: LoadedBatches<List>,
  keyOf: (item: List["items"][number]) => string,
) {
  const seen = new Set(previous.list.items.map(keyOf));
  const fresh = next.list.items.filter((item) => !seen.has(keyOf(item)));
  return loadedBatches({ ...next.list, items: [...previous.list.items, ...fresh] }, next.list.items.length, fresh.length);
}

/**
 * "Load more" paging state of one scope: the current page and retry attempt.
 * A new scope restarts at page 1. `key` names the current read inside the
 * scope, for `useScopedRead`.
 */
export function useBatchPaging(scope: string) {
  // `attempt` gives a retried batch a new read key for the same page.
  const [paging, setPaging] = useState({ scope, page: 1, attempt: 0 });
  const { page, attempt } = paging.scope === scope ? paging : { page: 1, attempt: 0 };
  return {
    page,
    key: `${scope}#${page}:${attempt}`,
    loadMore: () => setPaging({ scope, page: page + 1, attempt: 0 }),
    /** Re-requests the batch that failed; earlier batches stay. */
    retry: () => setPaging({ scope, page, attempt: attempt + 1 }),
  };
}
