import { badgeClass, cx } from "@yinfengwindy/shiori-sdk";
import type { AffectionChangeTone, AffectionHistoryGroup, AffectionHistoryRow } from "./affectionSelectors";

const changeClass: Record<AffectionChangeTone, string> = {
  init: "text-ink",
  up: "text-success-text",
  down: "text-danger-text",
};

const nodeClass: Record<AffectionChangeTone, string> = {
  init: "bg-accent",
  up: "bg-success",
  down: "bg-danger",
};

const railColumnsClass = "grid grid-cols-[0.75rem_minmax(0,1fr)] gap-x-3";

/** A stretch of the rail; transparent before the first node and after the last. */
function RailSegment({ visible, className }: { visible: boolean; className: string }) {
  return <span aria-hidden="true" className={cx("w-px", visible ? "bg-line-soft" : "bg-transparent", className)} />;
}

/** One node on the rail: time, reason (with the size of a merged run), source badge (decay and init only) and change. */
function HistoryItem({ row, first, last }: { row: AffectionHistoryRow; first: boolean; last: boolean }) {
  return <li className={railColumnsClass} data-tone={row.tone}>
    <div className="flex flex-col items-center" aria-hidden="true">
      <RailSegment visible={!first} className="h-3.5 shrink-0" />
      <span className={cx("h-2.5 w-2.5 shrink-0 rounded-full", nodeClass[row.tone])} />
      <RailSegment visible={!last} className="flex-1" />
    </div>
    <div className="flex items-baseline gap-3 py-2">
      <time className="w-12 shrink-0 text-caption tabular-nums text-ink-muted" dateTime={row.time}>{row.timeLabel}</time>
      <p className="m-0 min-w-0 flex-1 break-words text-body text-ink">
        {row.reason}
        {row.count > 1 && <span className="ml-1.5 tabular-nums text-ink-muted">×{row.count}</span>}
      </p>
      {row.sourceLabel && <span className={cx(badgeClass, "shrink-0")}>{row.sourceLabel}</span>}
      <span className={cx("w-10 shrink-0 text-right text-body-lg font-semibold tabular-nums", changeClass[row.tone])} data-testid="affection-change">{row.change}</span>
    </div>
  </li>;
}

/**
 * The history timeline, newest first: one continuous rail from the first node
 * to the last, running past the local date headings, with a node per row.
 */
export function AffectionHistoryList({ groups }: { groups: readonly AffectionHistoryGroup[] }) {
  return <div className="grid">
    {groups.map((group, groupIndex) => {
      const lastGroup = groupIndex === groups.length - 1;
      return <section key={`${group.key}:${group.items[0].key}`} className="grid" aria-label={group.label}>
        <div className={railColumnsClass}>
          <RailSegment visible={groupIndex > 0} className="justify-self-center" />
          <h4 className={cx("m-0 pb-0.5 text-caption font-medium text-ink-muted", groupIndex > 0 && "pt-3")}>{group.label}</h4>
        </div>
        <ol className="m-0 grid list-none p-0">
          {group.items.map((row, index) => <HistoryItem key={row.key} row={row}
            first={groupIndex === 0 && index === 0} last={lastGroup && index === group.items.length - 1} />)}
        </ol>
      </section>;
    })}
  </div>;
}
