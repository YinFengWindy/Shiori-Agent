import { appendBatch, firstBatch, type LoadedBatches } from "../shared/batchPaging";
import { formatTimestamp } from "../shared/format";
import type { AffectionHistoryEntry, AffectionHistoryPage, AffectionSource } from "./affectionHistory";

/** The loaded history: every batch so far, and whether asking for another is pointless. */
export type AffectionHistoryBatches = LoadedBatches<AffectionHistoryPage>;

/** The first batch of a role's history. */
export function firstAffectionBatch(page: AffectionHistoryPage): AffectionHistoryBatches {
  return firstBatch(page);
}

/** Appends the next batch under the loaded ones, dropping repeats by entry id; the newest summary wins. */
export function appendAffectionBatch(previous: AffectionHistoryBatches, next: AffectionHistoryBatches): AffectionHistoryBatches {
  return appendBatch(previous, next, (entry) => String(entry.id));
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
  return entries.map((entry) => {
    const isInit = entry.source === "init" || entry.delta === null;
    const delta = entry.delta ?? 0;
    return {
      key: String(entry.id),
      time: entry.time,
      timeLabel: formatTimestamp(entry.time) || entry.time,
      change: isInit ? String(entry.after) : delta > 0 ? `+${delta}` : String(delta),
      tone: isInit ? "init" : delta > 0 ? "up" : "down",
      sourceLabel: affectionSourceLabels[entry.source],
      reason: entry.reason,
    };
  });
}
