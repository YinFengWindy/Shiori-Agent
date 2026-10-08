import { badgeClass, cx } from "@yinfengwindy/shiori-sdk";
import type { AffectionChangeTone, AffectionHistoryRow } from "./affectionSelectors";

const toneClass: Record<AffectionChangeTone, string> = {
  init: "text-ink",
  up: "text-success-text",
  down: "text-danger-text",
};

/** History rows, newest first: change, time, source and reason. */
export function AffectionHistoryList({ rows }: { rows: readonly AffectionHistoryRow[] }) {
  return <ol className="m-0 grid list-none gap-1 p-0">
    {rows.map((row) => <li key={row.key} className="grid grid-cols-[3rem_minmax(0,1fr)] items-baseline gap-x-3 rounded-md px-2 py-2">
      <span className={cx("text-body-lg font-semibold tabular-nums", toneClass[row.tone])} data-testid="affection-change">{row.change}</span>
      <div className="grid min-w-0 gap-1">
        <div className="flex items-center gap-2">
          <time className="text-caption tabular-nums text-ink-muted" dateTime={row.time}>{row.timeLabel}</time>
          <span className={cx(badgeClass, "shrink-0")}>{row.sourceLabel}</span>
        </div>
        <p className="m-0 break-words text-body text-ink">{row.reason}</p>
      </div>
    </li>)}
  </ol>;
}
