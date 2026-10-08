import assert from "node:assert/strict";
import { it } from "node:test";
import type { AffectionHistoryEntry, AffectionHistoryPage } from "./affectionHistory";
import { formatDate } from "../shared/format";
import { affectionHistoryGroups, affectionHistoryRows, appendAffectionBatch, firstAffectionBatch } from "./affectionSelectors";

const entry = (overrides: Partial<AffectionHistoryEntry>): AffectionHistoryEntry => ({
  id: 1, time: "2026-10-08T12:00:00+08:00", before: 30, after: 32, delta: 2, reason: "夸奖", source: "turn", ...overrides,
});
const page = (items: AffectionHistoryEntry[], total: number, number = 1): AffectionHistoryPage => ({
  role_id: "mira", affection: { value: 32, stage: "熟悉", progress: 12 / 19, floor: 20 }, items, total, page: number, page_size: 2,
});

it("formats signed deltas and shows the initial value on the init row", () => {
  const rows = affectionHistoryRows([
    entry({ id: 2, delta: 2, after: 33, reason: "夸奖" }),
    entry({ id: 1, delta: -1, before: 33, after: 32, source: "decay", reason: "久未联系" }),
    entry({ id: 0, before: null, after: 30, delta: null, source: "init", reason: "老朋友" }),
  ]);

  assert.deepEqual(rows.map(({ key, change, tone, sourceLabel, reason }) => ({ key, change, tone, sourceLabel, reason })), [
    { key: "2", change: "+2", tone: "up", sourceLabel: null, reason: "夸奖" },
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

it("merges each run of consecutive decay entries into one row summing their deltas", () => {
  const decay = (id: number, day: number): AffectionHistoryEntry =>
    entry({ id, time: `2026-10-0${day}T12:00:00+08:00`, before: 40 - id, after: 39 - id, delta: -1, source: "decay", reason: "长时间没有联系" });
  const rows = affectionHistoryRows([
    decay(6, 8), decay(5, 7), decay(4, 6),
    entry({ id: 3, time: "2026-10-03T09:00:00+08:00", delta: 2, reason: "夸奖" }),
    decay(2, 2),
    entry({ id: 0, time: "2026-10-01T09:00:00+08:00", before: null, after: 30, delta: null, source: "init", reason: "初始" }),
  ]);
  assert.deepEqual(rows.map(({ key, change, tone, reason, count }) => ({ key, change, tone, reason, count })), [
    { key: "6", change: "-3", tone: "down", reason: "长时间没有联系", count: 3 },
    { key: "3", change: "+2", tone: "up", reason: "夸奖", count: 1 },
    { key: "2", change: "-1", tone: "down", reason: "长时间没有联系", count: 1 },
    { key: "0", change: "30", tone: "init", reason: "初始", count: 1 },
  ]);
});

it("groups rows under the local date of their newest entry, newest first", () => {
  const groups = affectionHistoryGroups([
    entry({ id: 4, time: "2026-10-08T21:00:00", delta: -1, source: "decay", reason: "长时间没有联系" }),
    entry({ id: 3, time: "2026-10-07T21:00:00", delta: -1, source: "decay", reason: "长时间没有联系" }),
    entry({ id: 2, time: "2026-10-06T20:00:00", delta: 1 }),
    entry({ id: 1, time: "2026-10-06T08:00:00", delta: 2 }),
    entry({ id: 0, time: "2026-10-05T08:00:00", before: null, delta: null, source: "init" }),
  ]);
  assert.deepEqual(groups.map((group) => [group.label, group.items.map((row) => row.key)]), [
    [formatDate("2026-10-08T21:00:00"), ["4"]],
    [formatDate("2026-10-06T20:00:00"), ["2", "1"]],
    [formatDate("2026-10-05T08:00:00"), ["0"]],
  ]);
  assert.equal(groups[0].items[0].count, 2);
});
