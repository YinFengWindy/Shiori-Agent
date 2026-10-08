import { formatTimestamp } from "../shared/format";
import type { AffectionHistoryEntry, AffectionHistoryPage, AffectionSource } from "./affectionHistory";

/** The loaded history: every batch so far, and whether asking for another is pointless. */
export type AffectionHistoryBatches = { page: AffectionHistoryPage; exhausted: boolean };

function entryKey(entry: AffectionHistoryEntry) {
  return `${entry.time}|${entry.source}|${entry.after}`;
}

/**
 * Same end rule as the memory timeline: a short batch, a batch adding nothing
 * new, or loaded entries covering the total. A change recorded between
 * batches shifts the offsets; repeats are dropped and reopening starts over.
 */
function batchesFrom(page: AffectionHistoryPage, returned: number, fresh: number): AffectionHistoryBatches {
  const exhausted = fresh === 0 || returned < page.page_size || page.items.length >= page.total;
  return { page, exhausted };
}

/** The first batch of a role's history. */
export function firstAffectionBatch(page: AffectionHistoryPage) {
  return batchesFrom(page, page.items.length, page.items.length);
}

/** Appends the next batch under the loaded ones; the newest summary wins. */
export function appendAffectionBatch(previous: AffectionHistoryBatches, next: AffectionHistoryBatches) {
  const seen = new Set(previous.page.items.map(entryKey));
  const fresh = next.page.items.filter((entry) => !seen.has(entryKey(entry)));
  return batchesFrom({ ...next.page, items: [...previous.page.items, ...fresh] }, next.page.items.length, fresh.length);
}

/** Labels of each change source. */
export const affectionSourceLabels: Record<AffectionSource, string> = {
  init: "初始",
  turn: "对话",
  decay: "衰减",
};

/** Direction of a history row, for its change color. */
export type AffectionChangeTone = "init" | "up" | "down";

/** One displayed history row. */
export type AffectionHistoryRow = {
  key: string;
  time: string;
  timeLabel: string;
  /** Signed delta (`+2` / `-1`); the init row shows the initial value instead. */
  change: string;
  tone: AffectionChangeTone;
  sourceLabel: string;
  reason: string;
};

/** Derives the displayed rows, keeping the bridge's newest-first order. */
export function affectionHistoryRows(entries: readonly AffectionHistoryEntry[]): AffectionHistoryRow[] {
  return entries.map((entry, index) => {
    const isInit = entry.source === "init" || entry.delta === null;
    const delta = entry.delta ?? 0;
    return {
      key: `${entryKey(entry)}#${index}`,
      time: entry.time,
      timeLabel: formatTimestamp(entry.time) || entry.time,
      change: isInit ? String(entry.after) : delta > 0 ? `+${delta}` : String(delta),
      tone: isInit ? "init" : delta > 0 ? "up" : "down",
      sourceLabel: affectionSourceLabels[entry.source],
      reason: entry.reason,
    };
  });
}
