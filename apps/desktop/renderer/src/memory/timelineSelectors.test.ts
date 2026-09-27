import assert from "node:assert/strict";
import { it } from "node:test";
import { formatDate, formatTimestamp } from "../shared/format";
import type { RoleSemanticList } from "./roleSemanticMemory";
import { appendTimelineBatch, firstTimelineBatch, groupTimeline, itemOccurredAt, memoryDetailRows, type TimelineBatches } from "./timelineSelectors";

it("groups by local occurrence date, falling back to the record time, in engine order", () => {
  const items = [
    { id: "a", summary: "A", happened_at: "2026-09-02T21:00:00", created_at: "2026-09-10T01:00:00+00:00" },
    { id: "b", summary: "B", happened_at: null, created_at: "2026-09-02T08:00:00" },
    { id: "c", summary: "C", happened_at: "2026-09-01T23:59:00" },
    { id: "d", summary: "D" },
  ];
  assert.equal(itemOccurredAt(items[0]), "2026-09-02T21:00:00");
  assert.equal(itemOccurredAt(items[1]), "2026-09-02T08:00:00");
  const groups = groupTimeline(items);
  assert.deepEqual(groups.map((group) => group.items.map((item) => item.id)), [["a", "b"], ["c"], ["d"]]);
  assert.deepEqual(groups.map((group) => group.label), [formatDate("2026-09-02T21:00:00"), formatDate("2026-09-01T23:59:00"), "时间未知"]);
});

const batch = (ids: string[], total = 10, page = 1): RoleSemanticList => ({
  role_id: "mira", status: "ready", items: ids.map((id) => ({ id, summary: "" })), total, page, page_size: 2, filters: {},
});
const ids = (batches: TimelineBatches) => batches.list.items.map((item) => item.id);

it("appends a batch without repeating items and keeps going while full batches add something", () => {
  const merged = appendTimelineBatch(firstTimelineBatch(batch(["a", "b"])), firstTimelineBatch(batch(["b", "c"], 10, 2)));
  assert.deepEqual(ids(merged), ["a", "b", "c"]);
  assert.equal(merged.exhausted, false);
});

it("stops at a short batch, a batch with nothing new, the engine's total, or a disabled engine", () => {
  const first = firstTimelineBatch(batch(["a", "b"]));
  assert.equal(first.exhausted, false);
  assert.equal(firstTimelineBatch(batch(["a"])).exhausted, true);
  assert.equal(firstTimelineBatch(batch(["a", "b"], 2)).exhausted, true);
  assert.equal(appendTimelineBatch(first, firstTimelineBatch(batch(["c"], 10, 2))).exhausted, true);
  const repeated = appendTimelineBatch(first, firstTimelineBatch(batch(["a", "b"], 10, 2)));
  assert.deepEqual(ids(repeated), ["a", "b"]);
  assert.equal(repeated.exhausted, true);
  assert.equal(firstTimelineBatch({ role_id: "mira", status: "disabled", items: [], total: 0 }).exhausted, true);
});

it("lists detail fields with Chinese labels and localized times, known fields first", () => {
  const rows = memoryDetailRows({
    id: "m1",
    summary: "Tea",
    source_ref: "role:mira:1",
    status: "superseded",
    memory_domain: "",
    created_at: "2026-09-02T01:00:00+00:00",
    happened_at: "2026-09-02T09:00:00",
    emotional_weight: 0,
    extra_json: { memory_domain: "taste", mood: "calm", role_id: "mira" },
  });
  assert.deepEqual(rows.map((row) => [row.label, row.value]), [
    ["状态", "已失效"],
    ["领域", "taste"],
    ["来源", "role:mira:1"],
    ["发生时间", formatTimestamp("2026-09-02T09:00:00")],
    ["记录时间", formatTimestamp("2026-09-02T01:00:00+00:00")],
    ["情感权重", "0"],
    ["角色", "mira"],
    ["mood", "calm"],
  ]);
});
