import assert from "node:assert/strict";
import { it } from "node:test";
import type { AffectionHistoryEntry, AffectionHistoryPage } from "./affectionHistory";
import { affectionHistoryRows, appendAffectionBatch, firstAffectionBatch } from "./affectionSelectors";

const entry = (overrides: Partial<AffectionHistoryEntry>): AffectionHistoryEntry => ({
  time: "2026-10-08T12:00:00+08:00", before: 30, after: 32, delta: 2, reason: "夸奖", source: "turn", ...overrides,
});
const page = (items: AffectionHistoryEntry[], total: number, number = 1): AffectionHistoryPage => ({
  role_id: "mira", affection: { value: 32, stage: "熟悉", progress: 12 / 19 }, items, total, page: number, page_size: 2,
});

it("formats signed deltas and shows the initial value on the init row", () => {
  const rows = affectionHistoryRows([
    entry({ delta: 2, after: 33, reason: "夸奖" }),
    entry({ delta: -1, before: 33, after: 32, source: "decay", reason: "久未联系" }),
    entry({ before: null, after: 30, delta: null, source: "init", reason: "老朋友" }),
  ]);

  assert.deepEqual(rows.map(({ change, tone, sourceLabel, reason }) => ({ change, tone, sourceLabel, reason })), [
    { change: "+2", tone: "up", sourceLabel: "对话", reason: "夸奖" },
    { change: "-1", tone: "down", sourceLabel: "衰减", reason: "久未联系" },
    { change: "30", tone: "init", sourceLabel: "初始", reason: "老朋友" },
  ]);
  assert.equal(new Set(rows.map((row) => row.key)).size, 3);
});

it("keeps loading until the batches reach the total, dropping repeats", () => {
  const newest = entry({ time: "2026-10-08T12:03:00+08:00" });
  const middle = entry({ time: "2026-10-08T12:02:00+08:00" });
  const init = entry({ time: "2026-10-08T12:00:00+08:00", before: null, delta: null, source: "init" });

  const first = firstAffectionBatch(page([newest, middle], 3));
  assert.equal(first.exhausted, false);
  // A repeat of `middle` (offsets shifted) is dropped; the init entry ends the history.
  const second = appendAffectionBatch(first, firstAffectionBatch(page([middle, init], 3, 2)));
  assert.deepEqual(second.page.items, [newest, middle, init]);
  assert.equal(second.exhausted, true);
});
