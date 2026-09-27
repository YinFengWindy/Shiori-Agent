import type { ReactNode } from "react";
import { formatClock } from "../shared/format";
import { badgeClass, cx } from "../shared/styles";
import { emptySummaryLabel, groupTimeline, isSuperseded, itemOccurredAt } from "./timelineSelectors";
import type { RoleSemanticItem } from "./roleSemanticMemory";

type MemoryTimelineGroupsProps = {
  items: readonly RoleSemanticItem[];
  expandedIds: readonly string[];
  onToggle: (id: string) => void;
  renderDetail: (item: RoleSemanticItem) => ReactNode;
};

/** Node dot on the timeline rail; hollow for superseded items. */
function TimelineDot({ superseded }: { superseded: boolean }) {
  return superseded
    ? <span role="img" aria-label="已失效" className="mt-3 h-2.5 w-2.5 shrink-0 rounded-full border-2 border-line-strong bg-surface" />
    : <span aria-hidden="true" className="mt-3 h-2.5 w-2.5 shrink-0 rounded-full border-2 border-accent bg-accent" />;
}

function TimelineItem({ item, open, onToggle, detail }: { item: RoleSemanticItem; open: boolean; onToggle: () => void; detail: ReactNode }) {
  const superseded = isSuperseded(item);
  return <li className="grid grid-cols-[0.75rem_minmax(0,1fr)] gap-x-3">
    <div className="flex flex-col items-center">
      <TimelineDot superseded={superseded} />
      <span aria-hidden="true" className="w-px flex-1 bg-line-soft" />
    </div>
    <div className="grid gap-2 pb-2">
      <button type="button" aria-expanded={open} onClick={onToggle} className="flex w-full items-baseline gap-3 rounded-md px-2 py-2 text-left hover:bg-surface-hover">
        <time className="shrink-0 text-caption tabular-nums text-ink-muted" dateTime={itemOccurredAt(item)}>{formatClock(itemOccurredAt(item))}</time>
        <span className={cx("min-w-0 flex-1 break-words text-body", !open && "line-clamp-2", item.summary && !superseded ? "text-ink" : "text-ink-muted")}>
          {item.summary || emptySummaryLabel}
        </span>
        {item.memory_type ? <span className={cx(badgeClass, "shrink-0")}>{item.memory_type}</span> : null}
      </button>
      {open ? detail : null}
    </div>
  </li>;
}

/** Items grouped under local date headings, each expandable in place. */
export function MemoryTimelineGroups({ items, expandedIds, onToggle, renderDetail }: MemoryTimelineGroupsProps) {
  return <div className="grid gap-4">
    {groupTimeline(items).map((group) => <section key={`${group.key}:${group.items[0].id}`} className="grid gap-1" aria-label={group.label}>
      <h3 className="m-0 text-caption font-medium text-ink-muted">{group.label}</h3>
      <ol className="m-0 grid list-none p-0">
        {group.items.map((item) => {
          const open = expandedIds.includes(item.id);
          return <TimelineItem key={item.id} item={item} open={open} onToggle={() => onToggle(item.id)} detail={open ? renderDetail(item) : null} />;
        })}
      </ol>
    </section>)}
  </div>;
}
