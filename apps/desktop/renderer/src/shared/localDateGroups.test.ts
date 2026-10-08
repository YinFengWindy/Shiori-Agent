import assert from "node:assert/strict";
import { it } from "node:test";
import { formatDate } from "./format";
import { groupByLocalDate, localDateKey } from "./localDateGroups";

it("groups consecutive items by local date in list order, unreadable times together", () => {
  const items = [
    { id: "a", at: "2026-09-02T21:00:00" },
    { id: "b", at: "2026-09-02T08:00:00" },
    { id: "c", at: "2026-09-01T23:59:00" },
    { id: "d", at: "" },
    { id: "e", at: "later" },
  ];
  const groups = groupByLocalDate(items, (item) => item.at);
  assert.deepEqual(groups.map((group) => group.items.map((item) => item.id)), [["a", "b"], ["c"], ["d", "e"]]);
  assert.deepEqual(groups.map((group) => group.label), [formatDate("2026-09-02T21:00:00"), formatDate("2026-09-01T23:59:00"), "时间未知"]);
  assert.equal(localDateKey("2026-09-02T08:00:00"), "2026-9-2");
});
