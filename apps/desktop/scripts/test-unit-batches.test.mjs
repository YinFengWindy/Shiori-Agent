import assert from "node:assert/strict";
import test from "node:test";
import { batchByArgumentLength } from "./test-unit-batches.mjs";

test("files that fit the budget stay in one batch", () => {
  assert.deepEqual(batchByArgumentLength(["a.test.ts", "b.test.ts"], 100), [
    ["a.test.ts", "b.test.ts"],
  ]);
});

test("batches split in input order without exceeding the budget", () => {
  // Each 7-char path costs 10 (path + space + two quotes), so 25 fits two.
  const files = ["1.ts.ts", "2.ts.ts", "3.ts.ts", "4.ts.ts", "5.ts.ts"];
  const batches = batchByArgumentLength(files, 25);
  assert.deepEqual(batches, [["1.ts.ts", "2.ts.ts"], ["3.ts.ts", "4.ts.ts"], ["5.ts.ts"]]);
  assert.deepEqual(batches.flat(), files);
});

test("a single path longer than the budget is rejected", () => {
  assert.throws(() => batchByArgumentLength(["x".repeat(30)], 25), /exceeds the per-batch budget/);
});

test("no files produce no batches", () => {
  assert.deepEqual(batchByArgumentLength([], 25), []);
});
