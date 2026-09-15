import assert from "node:assert/strict";
import { test } from "node:test";
import { activePluginIds } from "./activePluginIds";

test("renderer admission requires ACTIVE and rejects every duplicate in any order", () => {
  const rejected = ["UNTRUSTED", "CONFLICT", "BLOCKED", "FAILED", "DISCOVERED", "DISABLED"];
  const rows = rejected.map((state) => ({ id: state, state, enabled: true }));
  rows.push({ id: "healthy", state: "ACTIVE", enabled: true });
  rows.push({ id: "disabled", state: "ACTIVE", enabled: false });
  rows.push({ id: "duplicate", state: "ACTIVE", enabled: true });
  rows.push({ id: "duplicate", state: "CONFLICT", enabled: true });
  for (const input of [rows, [...rows].reverse()]) {
    assert.deepEqual([...activePluginIds(input)], ["healthy"]);
  }
});
