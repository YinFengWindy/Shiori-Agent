import { appendBatch, firstBatch, type LoadedBatches } from "../shared/batchPaging";
import { formatClock } from "../shared/format";
import { groupByLocalDate, type LocalDateGroup } from "../shared/localDateGroups";
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

/** Direction of a history row, for its node and change colors. */
export type AffectionChangeTone = "init" | "up" | "down";

/** One displayed history row: one entry, or a run of consecutive decay entries. */
export type AffectionHistoryRow = {
  key: string;
  /** The (newest) entry's time. */
  time: string;
  timeLabel: string;
  /** Signed delta (`+2` / `-1`), summed over a decay run; the init row shows the initial value instead. */
  change: string;
  tone: AffectionChangeTone;
  /** Shown only for the unusual sources (衰减, 初始); null for an ordinary conversation turn. */
  sourceLabel: string | null;
  reason: string;
  /** How many entries the row stands for: above 1 only for a merged decay run. */
  count: number;
};

function signed(delta: number) {
  return delta > 0 ? `+${delta}` : String(delta);
}

/**
 * Derives the displayed rows, keeping the bridge's newest-first order. Each
 * run of consecutive decay entries becomes one row whose change is the sum of
 * theirs, keyed by its newest entry so it stays put as older batches load.
 */
export function affectionHistoryRows(entries: readonly AffectionHistoryEntry[]): AffectionHistoryRow[] {
  const rows: AffectionHistoryRow[] = [];
  let run: { row: AffectionHistoryRow; delta: number } | null = null;
  for (const entry of entries) {
    const isInit = entry.source === "init" || entry.delta === null;
    const delta = entry.delta ?? 0;
    if (entry.source === "decay" && run) {
      run.delta += delta;
      run.row.count += 1;
      run.row.change = signed(run.delta);
      run.row.tone = run.delta > 0 ? "up" : "down";
      continue;
    }
    const row: AffectionHistoryRow = {
      key: String(entry.id),
      time: entry.time,
      timeLabel: formatClock(entry.time) || entry.time,
      change: isInit ? String(entry.after) : signed(delta),
      tone: isInit ? "init" : delta > 0 ? "up" : "down",
      sourceLabel: entry.source === "turn" ? null : affectionSourceLabels[entry.source],
      reason: entry.reason,
      count: 1,
    };
    rows.push(row);
    run = entry.source === "decay" ? { row, delta } : null;
  }
  return rows;
}

/** One date heading of the history timeline and its rows. */
export type AffectionHistoryGroup = LocalDateGroup<AffectionHistoryRow>;

/** The history timeline: rows (decay runs merged) under the local date of each row's newest entry. */
export function affectionHistoryGroups(entries: readonly AffectionHistoryEntry[]): AffectionHistoryGroup[] {
  return groupByLocalDate(affectionHistoryRows(entries), (row) => row.time);
}
