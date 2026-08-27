/// <reference types="node" />

import assert from "node:assert/strict";
import test from "node:test";
import { isModelEffort, normalizeModelEffort } from "./modelEffort.js";

test("model effort normalizer accepts only bridge-supported values", () => {
  assert.equal(isModelEffort("high"), true);
  assert.equal(isModelEffort("xhigh"), false);
  assert.equal(normalizeModelEffort("max", "none"), "max");
  assert.equal(normalizeModelEffort("legacy", "high"), "high");
  assert.equal(normalizeModelEffort(null, "none"), "none");
});
