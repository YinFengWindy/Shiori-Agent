/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { minStoryLoadingMs, resolveStoryLoadingCopy, resolveStoryLoadingPresentation, waitForMinimumStoryLoading } from "./storyLoadingPresentation";

describe("resolveStoryLoadingCopy", () => {
  it("uses menu semantics while loading the Story launcher", () => {
    assert.deepEqual(resolveStoryLoadingCopy("listing", "reading-list"), {
      heading: "准备故事主菜单",
      currentStage: "读取故事列表",
      stageLabel: "主菜单加载阶段",
      stages: ["读取故事列表", "准备菜单", "完成"],
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
});

describe("waitForMinimumStoryLoading", () => {
  it("keeps the transition visible long enough to read its active stage", () => {
    assert.ok(minStoryLoadingMs >= 2_000);
  });

  it("waits for the remaining duration when loading finishes quickly", async () => {
    const delays: number[] = [];
    await waitForMinimumStoryLoading(1_000, 1_200, async (delayMs) => { delays.push(delayMs); });
    assert.deepEqual(delays, [minStoryLoadingMs - 200]);
  });

  it("does not add a delay after the minimum duration has elapsed", async () => {
    let slept = false;
    await waitForMinimumStoryLoading(1_000, 4_000, async () => { slept = true; });
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
