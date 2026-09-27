import { DetailRow } from "../shared/ui/DetailRow";
import { memoryReadKey, readSemanticDetail, type MemoryReadContext } from "./memoryReads";
import { MemoryReadError, MemoryStatusLine, memoryStatusText } from "./MemoryStatus";
import type { RoleSemanticDetail } from "./roleSemanticMemory";
import { emptySummaryLabel, memoryDetailRows } from "./timelineSelectors";
import { useMemoryRead } from "./useMemoryRead";

/**
 * In-place, read-only details of one timeline item, read when it is expanded.
 * A refresh collapses every item, so an open detail never outlives its context.
 */
export function MemoryItemDetail({ context, itemId }: { context: MemoryReadContext; itemId: string }) {
  const key = memoryReadKey(context, "detail", itemId);
  const detail = useMemoryRead<RoleSemanticDetail>({ scope: key, key, read: () => readSemanticDetail(context, itemId) });
  const item = detail.value?.item;
  return <section className="grid gap-2 rounded-md bg-surface-soft px-3 py-3" aria-label="记忆详情">
    {detail.loading ? <MemoryStatusLine text={memoryStatusText.loading} />
      : detail.error ? <MemoryReadError error={detail.error} />
      : detail.value?.status === "disabled" || !item ? <MemoryStatusLine text={memoryStatusText.disabled} />
      : <>
        <p className="m-0 whitespace-pre-wrap break-words px-3 text-body text-ink">{item.summary || emptySummaryLabel}</p>
        <div className="grid sm:grid-cols-2">
          {memoryDetailRows(item).map((row) => <DetailRow key={row.key} label={row.label} value={row.value} />)}
        </div>
      </>}
  </section>;
}
