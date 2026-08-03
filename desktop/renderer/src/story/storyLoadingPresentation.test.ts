/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolveStoryLoadingCopy, resolveStoryLoadingPresentation, storyLoadingCompletionHoldMs, storyLoadingStageMinMs, waitForMinimumStoryLoadingStage, waitForStoryLoadingCompletion } from "./storyLoadingPresentation";

describe("resolveStoryLoadingCopy", () => {
  it("uses menu semantics while loading the Story launcher", () => {
    assert.deepEqual(resolveStoryLoadingCopy("listing", "reading-list"), {
      heading: "Preparing",
      currentStage: "Read story list",
      stageLabel: "Story menu loading stages",
      stages: ["Read story list", "Prepare menu"],
      progressLabel: "Read story list",
      railLabel: "Story menu loading",
      activeStage: 0,
    });
  });

  it("keeps gameplay-entry semantics for saved Story loading", () => {
    const copy = resolveStoryLoadingCopy("story", "preparing-opening");
    assert.equal(copy.heading, "Preparing");
    assert.equal(copy.currentStage, "Prepare opening");
    assert.equal(copy.activeStage, 2);
    assert.deepEqual(copy.stages, ["Read story", "Restore progress", "Prepare opening"]);
    assert.equal(copy.railLabel, "Story loading");
  });

  it("marks the final menu phase after all loading stages", () => {
    const copy = resolveStoryLoadingCopy("listing", "menu-ready");
    assert.equal(copy.activeStage, copy.stages.length);
    assert.equal(copy.stages.length, 2);
  });
});

describe("waitForMinimumStoryLoadingStage", () => {
  it("keeps each active stage visible long enough to read", () => {
    assert.ok(storyLoadingStageMinMs >= 800);
  });

  it("waits for the remaining stage duration when work finishes quickly", async () => {
    const delays: number[] = [];
    await waitForMinimumStoryLoadingStage(1_000, 1_200, async (delayMs) => { delays.push(delayMs); });
    assert.deepEqual(delays, [storyLoadingStageMinMs - 200]);
  });

  it("does not add a delay after the stage duration has elapsed", async () => {
    let slept = false;
    await waitForMinimumStoryLoadingStage(1_000, 4_000, async () => { slept = true; });
    assert.equal(slept, false);
  });
});

describe("waitForStoryLoadingCompletion", () => {
  it("holds the all-complete state briefly", async () => {
    const delays: number[] = [];
    await waitForStoryLoadingCompletion(async (delayMs) => { delays.push(delayMs); });
    assert.deepEqual(delays, [storyLoadingCompletionHoldMs]);
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
