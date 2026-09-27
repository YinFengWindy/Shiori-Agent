import { cx, ghostButtonClass } from "../shared/styles";
import { MemoryFilterBar } from "./MemoryFilterBar";
import { MemoryItemDetail } from "./MemoryItemDetail";
import type { MemoryRpc } from "./memoryReads";
import { MemoryFrame, MemoryReadError, MemoryStatusLine, memoryStatusText } from "./MemoryStatus";
import { hasMoreSemantic } from "./timelineSelectors";
import { MemoryTimelineGroups } from "./MemoryTimelineGroups";
import { useMemoryTimeline } from "./useMemoryTimeline";

type MemoryTimelineProps = {
  client: MemoryRpc;
  roleId: string;
  /** The page's refresh counter; each bump restarts at the first batch. */
  refreshKey: number;
};

/** Semantic memories as a date-grouped timeline with declared filters and "load more". */
export function MemoryTimeline({ client, roleId, refreshKey }: MemoryTimelineProps) {
  const timeline = useMemoryTimeline(client, roleId, refreshKey);
  const { list } = timeline;
  const firstBatchPending = timeline.loading && !list;
  return <div className="grid gap-3">
    {list?.status !== "disabled" && <MemoryFilterBar query={timeline.query} filters={timeline.filters} onChange={timeline.updateQuery} />}
    <MemoryFrame label="时间线">
      {firstBatchPending ? <MemoryStatusLine text={memoryStatusText.loading} />
        : !list ? <MemoryReadError error={timeline.error} />
        : list.status === "disabled" ? <MemoryStatusLine text={memoryStatusText.disabled} />
        : list.items.length === 0 ? <MemoryStatusLine text={memoryStatusText.noItems} />
        : <MemoryTimelineGroups
          items={list.items}
          expandedIds={timeline.expandedIds}
          onToggle={timeline.toggle}
          renderDetail={(item) => <MemoryItemDetail client={client} roleId={roleId} itemId={item.id} refreshKey={refreshKey} />}
        />}
      {list && timeline.loading && <MemoryStatusLine text={memoryStatusText.loading} />}
      {list && timeline.error && <MemoryReadError error={timeline.error} />}
      {!timeline.loading && !timeline.error && hasMoreSemantic(list) && <button type="button" className={cx(ghostButtonClass, "justify-self-center")} onClick={timeline.loadMore}>加载更多</button>}
    </MemoryFrame>
  </div>;
}
