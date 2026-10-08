import assert from "node:assert/strict";
import { it } from "node:test";
import type { AffectionHistoryEntry, AffectionHistoryPage } from "./affectionHistory";
import { affectionHistoryRows, appendAffectionBatch, firstAffectionBatch } from "./affectionSelectors";

const entry = (overrides: Partial<AffectionHistoryEntry>): AffectionHistoryEntry => ({
  id: 1, time: "2026-10-08T12:00:00+08:00", before: 30, after: 32, delta: 2, reason: "夸奖", source: "turn", ...overrides,
});
const page = (items: AffectionHistoryEntry[], total: number, number = 1): AffectionHistoryPage => ({
  role_id: "mira", affection: { value: 32, stage: "熟悉", progress: 12 / 19 }, items, total, page: number, page_size: 2,
});

it("formats signed deltas and shows the initial value on the init row", () => {
  const rows = affectionHistoryRows([
    entry({ id: 2, delta: 2, after: 33, reason: "夸奖" }),
    entry({ id: 1, delta: -1, before: 33, after: 32, source: "decay", reason: "久未联系" }),
    entry({ id: 0, before: null, after: 30, delta: null, source: "init", reason: "老朋友" }),
  ]);

  assert.deepEqual(rows.map(({ key, change, tone, sourceLabel, reason }) => ({ key, change, tone, sourceLabel, reason })), [
    { key: "2", change: "+2", tone: "up", sourceLabel: "对话", reason: "夸奖" },
    { key: "1", change: "-1", tone: "down", sourceLabel: "衰减", reason: "久未联系" },
    { key: "0", change: "30", tone: "init", sourceLabel: "初始", reason: "老朋友" },
  ]);
});

it("drops a repeated entry by id, keeping distinct entries that look alike", () => {
  // Entries 2 and 1 share time, source and value: only the id tells them apart.
  const init = entry({ id: 0, before: null, delta: null, source: "init" });
  const first = firstAffectionBatch(page([entry({ id: 3, after: 33 }), entry({ id: 2 })], 4));
  const second = appendAffectionBatch(first, firstAffectionBatch(page([entry({ id: 1 }), init], 4, 2)));
  assert.deepEqual(second.list.items.map((item) => item.id), [3, 2, 1, 0]);
  assert.equal(second.exhausted, true);
  // Offsets shifted by one: entry 2 comes again and is dropped.
  const shifted = appendAffectionBatch(first, firstAffectionBatch(page([entry({ id: 2 }), entry({ id: 1 })], 5, 2)));
  assert.deepEqual(shifted.list.items.map((item) => item.id), [3, 2, 1]);
});
