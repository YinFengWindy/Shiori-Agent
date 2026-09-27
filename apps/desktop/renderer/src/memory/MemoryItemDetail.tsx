import { DetailRow } from "../shared/ui/DetailRow";
import { memoryClientKey, readSemanticDetail, type MemoryRpc } from "./memoryReads";
import { emptySummaryLabel, memoryDetailRows } from "./timelineSelectors";
import { MemoryReadError, MemoryStatusLine, memoryStatusText } from "./MemoryStatus";
import type { RoleSemanticDetail } from "./roleSemanticMemory";
import { useMemoryRead } from "./useMemoryRead";

type MemoryItemDetailProps = {
  client: MemoryRpc;
  roleId: string;
  itemId: string;
  /** The page's refresh counter; a refresh re-reads an open detail. */
  refreshKey: number;
};

/** In-place, read-only details of one timeline item, read on demand. */
export function MemoryItemDetail({ client, roleId, itemId, refreshKey }: MemoryItemDetailProps) {
  const key = `${memoryClientKey(client)}:${roleId}:${itemId}:${refreshKey}`;
  const detail = useMemoryRead<RoleSemanticDetail>({ scope: key, key, read: () => readSemanticDetail(client, roleId, itemId) });
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
