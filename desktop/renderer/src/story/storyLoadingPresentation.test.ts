/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolveStoryLoadingCopy, resolveStoryLoadingPresentation, storyLoadingCompletionHoldMs, storyLoadingStageMinMs, waitForMinimumStoryLoadingStage, waitForStoryLoadingCompletion } from "./storyLoadingPresentation";

describe("resolveStoryLoadingCopy", () => {
  it("uses menu semantics while loading the Story launcher", () => {
    assert.deepEqual(resolveStoryLoadingCopy("listing", "reading-list"), {
      heading: "准备故事主菜单",
      currentStage: "读取故事列表",
      stageLabel: "主菜单加载阶段",
      stages: ["读取故事列表", "准备菜单"],
      progressLabel: "读取故事列表",
      railLabel: "故事主菜单加载",
      activeStage: 0,
    });
  });

  it("keeps gameplay-entry semantics for saved Story loading", () => {
    const copy = resolveStoryLoadingCopy("story", "preparing-opening");
    assert.equal(copy.heading, "进入剧情");
    assert.equal(copy.currentStage, "准备开场");
    assert.equal(copy.activeStage, 2);
    assert.deepEqual(copy.stages, ["读取剧情", "恢复进度", "准备开场"]);
    assert.equal(copy.railLabel, "剧情加载");
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
