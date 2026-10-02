import assert from "node:assert/strict";
import { test } from "node:test";
import { createModelRegistration, hasModelCapacity, isModelRegistrationComplete } from "./modelRegistration";

test("a registration completes with only a valid window; the auto compaction threshold is optional but bounded", () => {
  const draft = { ...createModelRegistration(), model: "same-model" };
  assert.equal(hasModelCapacity(draft), false);
  assert.equal(isModelRegistrationComplete(draft), false);
  assert.equal(isModelRegistrationComplete({ ...draft, modelContextWindow: 128000 }), true);
  assert.equal(isModelRegistrationComplete({ ...draft, modelContextWindow: 128000, modelAutoCompactTokenLimit: 100000 }), true);
  for (const capacities of [
    { modelContextWindow: 0 },
    { modelContextWindow: 1.5 },
    { modelContextWindow: 128000, modelAutoCompactTokenLimit: 0 },
    { modelContextWindow: 128000, modelAutoCompactTokenLimit: 128000 },
    { modelContextWindow: 128000, modelAutoCompactTokenLimit: 1.5 },
  ]) {
    assert.equal(hasModelCapacity({ ...draft, ...capacities }), false);
  }
});
