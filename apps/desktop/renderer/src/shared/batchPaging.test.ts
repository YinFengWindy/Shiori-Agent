import assert from "node:assert/strict";
import { it } from "node:test";
import { appendBatch, firstBatch, type BatchPage, type LoadedBatches } from "./batchPaging";

type Row = { key: string };
const batch = (keys: string[], total = 10): BatchPage<Row> => ({ items: keys.map((key) => ({ key })), total, page_size: 2 });
const append = (previous: LoadedBatches<BatchPage<Row>>, keys: string[], total = 10) => appendBatch(previous, firstBatch(batch(keys, total)), (row) => row.key);
const keys = (loaded: LoadedBatches<BatchPage<Row>>) => loaded.list.items.map((row) => row.key);

it("appends batches by key and keeps going while full batches add something", () => {
  const merged = append(firstBatch(batch(["a", "b"])), ["b", "c"]);
  assert.deepEqual(keys(merged), ["a", "b", "c"]);
  assert.equal(merged.exhausted, false);
});

it("stops at a short batch, a batch with nothing new, or the total", () => {
  const first = firstBatch(batch(["a", "b"]));
  assert.equal(first.exhausted, false);
  assert.equal(firstBatch(batch(["a"])).exhausted, true);
  assert.equal(firstBatch(batch(["a", "b"], 2)).exhausted, true);
  assert.equal(append(first, ["c"]).exhausted, true);
  const repeated = append(first, ["a", "b"]);
  assert.deepEqual(keys(repeated), ["a", "b"]);
  assert.equal(repeated.exhausted, true);
});
