import { cx, ghostButtonClass } from "@yinfengwindy/shiori-sdk";
import { MemoryFilterBar } from "./MemoryFilterBar";
import { MemoryItemDetail } from "./MemoryItemDetail";
import type { MemoryReadContext } from "./memoryReads";
import { ReadFrame, ReadError, ReadStatusLine } from "../shared/feedback/ReadStatus";
import { memoryStatusText } from "./memoryStatusText";
import { MemoryTimelineGroups } from "./MemoryTimelineGroups";
import { useMemoryTimeline } from "./useMemoryTimeline";

/** Semantic memories as a date-grouped timeline with declared filters and "load more". */
export function MemoryTimeline({ context }: { context: MemoryReadContext }) {
  const timeline = useMemoryTimeline(context);
  const { list } = timeline;
  return <div className="grid gap-3">
    {list?.status !== "disabled" && <MemoryFilterBar query={timeline.query} filters={timeline.filters} onChange={timeline.updateQuery} />}
    <ReadFrame label="时间线">
      {!list ? (timeline.loading ? <ReadStatusLine text={memoryStatusText.loading} /> : null)
        : list.status === "disabled" ? <ReadStatusLine text={memoryStatusText.disabled} />
        : list.items.length === 0 ? <ReadStatusLine text={memoryStatusText.noItems} />
        : <MemoryTimelineGroups
          items={list.items}
          expandedIds={timeline.expandedIds}
          onToggle={timeline.toggle}
          renderDetail={(item) => <MemoryItemDetail context={context} itemId={item.id} />}
        />}
      {/* Later batches load and fail under the items already shown. */}
      {list && timeline.loading && <ReadStatusLine text={memoryStatusText.loading} />}
      {timeline.error && <ReadError error={timeline.error} onRetry={timeline.retry} />}
      {!timeline.loading && !timeline.error && timeline.hasMore && <button type="button" className={cx(ghostButtonClass, "justify-self-center")} onClick={timeline.loadMore}>加载更多</button>}
    </ReadFrame>
  </div>;
}
