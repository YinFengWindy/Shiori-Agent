import { DetailRow } from "../shared/ui/DetailRow";
import { memoryReadKey, readSemanticDetail, type MemoryReadContext } from "./memoryReads";
import { ReadError, ReadStatusLine } from "../shared/feedback/ReadStatus";
import { memoryStatusText } from "./memoryStatusText";
import type { RoleSemanticDetail } from "./roleSemanticMemory";
import { emptySummaryLabel, memoryDetailRows } from "./timelineSelectors";
import { useScopedRead } from "../shared/useScopedRead";

/**
 * In-place, read-only details of one timeline item, read when it is expanded.
 * A refresh collapses every item, so an open detail never outlives its context.
 */
export function MemoryItemDetail({ context, itemId }: { context: MemoryReadContext; itemId: string }) {
  const key = memoryReadKey(context, "detail", itemId);
  const detail = useScopedRead<RoleSemanticDetail>({ scope: key, key, read: () => readSemanticDetail(context, itemId) });
  const item = detail.value?.item;
  return <section className="grid gap-2 rounded-md bg-surface-soft px-3 py-3" aria-label="记忆详情">
    {detail.loading ? <ReadStatusLine text={memoryStatusText.loading} />
      : detail.error ? <ReadError error={detail.error} />
      : detail.value?.status === "disabled" ? <ReadStatusLine text={memoryStatusText.disabled} />
      : !item ? <ReadStatusLine text={memoryStatusText.itemMissing} />
      : <>
        <p className="m-0 whitespace-pre-wrap break-words px-3 text-body text-ink">{item.summary || emptySummaryLabel}</p>
        <div className="grid sm:grid-cols-2">
          {memoryDetailRows(item).map((row) => <DetailRow key={row.key} label={row.label} value={row.value} />)}
        </div>
      </>}
  </section>;
}
