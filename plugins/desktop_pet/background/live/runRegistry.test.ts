import assert from "node:assert/strict";
import { test } from "node:test";
import { LiveRunRegistry } from "./runRegistry";

test("cancelling every run covers the runs seen so far, within a bounded memory", () => {
  const runs = new LiveRunRegistry(2);
  runs.see("a"); runs.see("b"); runs.cancel();
  assert.equal(runs.isCancelled("a"), true);
  runs.cancel("c");
  assert.equal(runs.isCancelled("a"), false, "the oldest is forgotten past the limit");
  assert.equal(runs.isCancelled("c"), true);
  runs.reset();
  assert.equal(runs.isCancelled("c"), false);
});
