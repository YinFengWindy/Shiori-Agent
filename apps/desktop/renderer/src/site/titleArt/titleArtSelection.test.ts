/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { nextIndex, pickInitialIndex } from "./titleArtSelection";

describe("pickInitialIndex", () => {
  it("is deterministic for an injected random source", () => {
    assert.equal(pickInitialIndex(3, () => 0), 0);
    assert.equal(pickInitialIndex(3, () => 0.34), 1);
    assert.equal(pickInitialIndex(3, () => 0.67), 2);
    // Just under 1 must still land on the last valid index, never count itself.
    assert.equal(pickInitialIndex(3, () => 0.999999), 2);
  });

  it("rejects a non-positive count", () => {
    assert.throws(() => pickInitialIndex(0, () => 0));
    assert.throws(() => pickInitialIndex(-1, () => 0));
  });

  it("rejects a random source outside [0, 1)", () => {
    assert.throws(() => pickInitialIndex(3, () => 1));
    assert.throws(() => pickInitialIndex(3, () => -0.1));
  });
});

describe("nextIndex", () => {
  it("advances by one within range", () => {
    assert.equal(nextIndex(0, 3), 1);
    assert.equal(nextIndex(1, 3), 2);
  });

  it("wraps around after the last index", () => {
    assert.equal(nextIndex(2, 3), 0);
  });

  it("wraps a single-item list back to itself", () => {
    assert.equal(nextIndex(0, 1), 0);
  });
});
