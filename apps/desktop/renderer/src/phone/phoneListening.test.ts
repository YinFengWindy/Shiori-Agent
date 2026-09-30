import assert from "node:assert/strict";
import { test } from "node:test";
import { dailyCapDraftDirty, parseDailyCap, phoneListeningToggleRows } from "./phoneListening";

test("a cap field holds a whole number of at least 1, or nothing for the default", () => {
  assert.equal(parseDailyCap(" 50 "), 50);
  assert.equal(parseDailyCap(""), null);
  for (const text of ["0", "-3", "2.5", "abc"]) assert.equal(parseDailyCap(text), undefined);
  assert.equal(dailyCapDraftDirty("050", "50"), false);
  assert.equal(dailyCapDraftDirty("", "50"), true);
});

test("the switch log names who changed listening, to what, and when", () => {
  // Local-time dates, so the rendered clock matches wherever the test runs.
  const now = new Date(2026, 8, 30, 20);
  const rows = phoneListeningToggleRows([
    { enabled: false, operator: "role", at: new Date(2026, 8, 30, 14, 5).toISOString() },
    { enabled: true, operator: "user", at: new Date(2026, 8, 29, 9).toISOString() },
  ], "Mira", now);
  assert.deepEqual(rows.map(({ who, action, time }) => `${who}${action} ${time}`), ["Mira关闭 14:05", "我开启 昨天 09:00"]);
});
