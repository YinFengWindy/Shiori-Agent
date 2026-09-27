import assert from "node:assert/strict";
import { it } from "node:test";
import { formatDate, formatTimestamp } from "../shared/format";
import type { RoleSemanticList } from "./roleSemanticMemory";
import { appendSemanticBatch, groupTimeline, hasMoreSemantic, itemOccurredAt, memoryDetailRows } from "./timelineSelectors";

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

it("appends a batch without repeating items and knows when more remain", () => {
  const first: RoleSemanticList = { role_id: "mira", status: "ready", items: [{ id: "a", summary: "" }, { id: "b", summary: "" }], total: 4, page: 1, page_size: 2, filters: {} };
  const second: RoleSemanticList = { ...first, items: [{ id: "b", summary: "" }, { id: "c", summary: "" }], page: 2 };
  const merged = appendSemanticBatch(first, second);
  assert.deepEqual(merged.items.map((item) => item.id), ["a", "b", "c"]);
  assert.equal(hasMoreSemantic(merged), true);
  assert.equal(hasMoreSemantic({ ...first, total: 2 }), false);
  assert.equal(hasMoreSemantic({ role_id: "mira", status: "disabled", items: [], total: 0 }), false);
  assert.equal(hasMoreSemantic(null), false);
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
