import assert from "node:assert/strict";
import { test } from "node:test";
import { createModelRegistration, hasModelCapacity, isModelRegistrationComplete } from "./modelRegistration";

test("new and legacy profiles require explicit valid capacities before registration completes", () => {
  const draft = { ...createModelRegistration(), model: "same-model" };
  assert.equal(hasModelCapacity(draft), false);
  assert.equal(isModelRegistrationComplete(draft), false);
  assert.equal(isModelRegistrationComplete({ ...draft, contextWindowTokens: 128000, maxOutputTokens: 32768 }), true);
  for (const capacities of [{ contextWindowTokens: 0, maxOutputTokens: 10 }, { contextWindowTokens: 100, maxOutputTokens: 101 }, { contextWindowTokens: 1.5, maxOutputTokens: 1 }]) {
    assert.equal(hasModelCapacity({ ...draft, ...capacities }), false);
  }
});
