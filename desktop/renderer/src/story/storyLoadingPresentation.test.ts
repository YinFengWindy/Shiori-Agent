/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { minStoryLoadingMs, resolveStoryLoadingPresentation, waitForMinimumStoryLoading } from "./storyLoadingPresentation";

describe("waitForMinimumStoryLoading", () => {
  it("waits for the remaining duration when loading finishes quickly", async () => {
    const delays: number[] = [];
    await waitForMinimumStoryLoading(1_000, 1_200, async (delayMs) => { delays.push(delayMs); });
    assert.deepEqual(delays, [minStoryLoadingMs - 200]);
  });

  it("does not add a delay after the minimum duration has elapsed", async () => {
    let slept = false;
    await waitForMinimumStoryLoading(1_000, 2_600, async () => { slept = true; });
    assert.equal(slept, false);
  });
});

describe("resolveStoryLoadingPresentation", () => {
  it("keeps sub-250ms loads invisible", () => {
    assert.equal(resolveStoryLoadingPresentation({ elapsedMs: 249, loaded: 0, total: 3 }).kind, "hidden");
  });

  it("uses a short transition before two seconds", () => {
    assert.equal(resolveStoryLoadingPresentation({ elapsedMs: 800, loaded: 1, total: 3 }).kind, "transition");
  });

  it("shows measurable progress after two seconds", () => {
    assert.deepEqual(resolveStoryLoadingPresentation({ elapsedMs: 2400, loaded: 3, total: 8 }), { kind: "progress", loaded: 3, total: 8, ratio: 3 / 8 });
  });
});
