import { cx, ghostButtonClass } from "@shiori/sdk";
import { MemoryFilterBar } from "./MemoryFilterBar";
import { MemoryItemDetail } from "./MemoryItemDetail";
import type { MemoryReadContext } from "./memoryReads";
import { MemoryFrame, MemoryReadError, MemoryStatusLine, memoryStatusText } from "./MemoryStatus";
import { MemoryTimelineGroups } from "./MemoryTimelineGroups";
import { useMemoryTimeline } from "./useMemoryTimeline";

/** Semantic memories as a date-grouped timeline with declared filters and "load more". */
export function MemoryTimeline({ context }: { context: MemoryReadContext }) {
  const timeline = useMemoryTimeline(context);
  const { list } = timeline;
  return <div className="grid gap-3">
    {list?.status !== "disabled" && <MemoryFilterBar query={timeline.query} filters={timeline.filters} onChange={timeline.updateQuery} />}
    <MemoryFrame label="时间线">
      {!list ? (timeline.loading ? <MemoryStatusLine text={memoryStatusText.loading} /> : null)
        : list.status === "disabled" ? <MemoryStatusLine text={memoryStatusText.disabled} />
        : list.items.length === 0 ? <MemoryStatusLine text={memoryStatusText.noItems} />
        : <MemoryTimelineGroups
          items={list.items}
          expandedIds={timeline.expandedIds}
          onToggle={timeline.toggle}
          renderDetail={(item) => <MemoryItemDetail context={context} itemId={item.id} />}
        />}
      {/* Later batches load and fail under the items already shown. */}
      {list && timeline.loading && <MemoryStatusLine text={memoryStatusText.loading} />}
      {timeline.error && <MemoryReadError error={timeline.error} onRetry={timeline.retry} />}
      {!timeline.loading && !timeline.error && timeline.hasMore && <button type="button" className={cx(ghostButtonClass, "justify-self-center")} onClick={timeline.loadMore}>加载更多</button>}
    </MemoryFrame>
  </div>;
}
