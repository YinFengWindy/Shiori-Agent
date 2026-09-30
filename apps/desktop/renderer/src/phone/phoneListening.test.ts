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
  const now = new Date("2026-09-30T20:00:00+08:00");
  const rows = phoneListeningToggleRows([
    { enabled: false, operator: "role", at: "2026-09-30T14:05:00+08:00" },
    { enabled: true, operator: "user", at: "2026-09-29T09:00:00+08:00" },
  ], "Mira", now);
  assert.deepEqual(rows.map(({ who, action, time }) => `${who}${action} ${time}`), ["Mira关闭 14:05", "我开启 昨天 09:00"]);
});
