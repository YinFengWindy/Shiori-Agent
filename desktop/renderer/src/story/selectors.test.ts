/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { canShowStoryInput, canSubmitStoryInput, getStoryStatusLabel, isStoryRoleInCurrentScene, mergeStoryBeats, replaceStoryGallery, replaceStorySummary, selectActiveStoryVisualResource } from "./selectors";
import { createStoryBeat, createStoryDetails, createStorySummary } from "./testFixtures";

describe("Story selectors", () => {
  it("allows input only while the active segment awaits the player", () => {
    assert.equal(canSubmitStoryInput(createStoryDetails()), true);
    assert.equal(canSubmitStoryInput(createStoryDetails({ segment: { ...createStoryDetails().segment, operation: "generating" } })), false);
  });

  it("hides the input until the visible beat is the latest beat", () => {
    const story = createStoryDetails();
    assert.equal(canShowStoryInput(story, false, false), true);
    assert.equal(canShowStoryInput(story, false, true), false);
    assert.equal(canShowStoryInput(story, true, false), false);
  });

  it("merges replayed beats without duplicates and restores repository order", () => {
    const first = createStoryBeat({ id: "first", sequence: 1 });
    const second = createStoryBeat({ id: "second", sequence: 2 });
    assert.deepEqual(mergeStoryBeats([second], [first, second]).map((beat) => beat.id), ["first", "second"]);
  });

  it("refreshes a launcher summary from a Story read model", () => {
    const summary = createStorySummary();
    const story = createStoryDetails({ title: "新标题", status: "archived", currentTimeBand: "夜晚", beats: [createStoryBeat({ timeBand: "夜晚" })] });
    const updated = replaceStorySummary([summary], story);
    assert.equal(updated[0].title, "新标题");
    assert.equal(updated[0].status, "archived");
    assert.equal(updated[0].currentTimeBand, "夜晚");
    assert.equal(getStoryStatusLabel("awaiting_player"), "轮到你了");
  });

  it("applies the retry response to the visible CG gallery immediately", () => {
    const failedResource = {
      id: "resource-1",
      storyId: "story-1",
      kind: "cg" as const,
      visualType: "scene" as const,
      sceneKey: "default",
      status: "failed" as const,
      path: null,
      prompt: "rainy school gate",
      sourceTurnId: "turn-2",
      sequence: 1,
      errorCode: "resource_generation_failed",
      createdAt: "2026-08-02T10:00:00+08:00",
      updatedAt: "2026-08-02T10:00:00+08:00",
    };
    const retryingResource = { ...failedResource, status: "generating" as const, errorCode: null };
    const story = createStoryDetails({ cgGallery: [retryingResource] });
    const current = [{ ...createStorySummary(), items: [failedResource] }];

    assert.equal(replaceStoryGallery(current, story)[0].items[0].status, "generating");
  });

  it("keeps a previous CG active while its replacement is generating", () => {
    const story = createStoryDetails({
      cgGallery: [{
        id: "resource-1",
        storyId: "story-1",
        kind: "cg",
        visualType: "scene",
        sceneKey: "default",
        status: "generating",
        path: "D:\\stories\\scene-old.png",
        prompt: "rainy school gate",
        sourceTurnId: "turn-2",
        sequence: 1,
        errorCode: null,
        createdAt: "",
        updatedAt: "",
      }],
    });

    assert.equal(selectActiveStoryVisualResource(story)?.path, "D:\\stories\\scene-old.png");
  });

  it("selects only visual resources owned by the current scene", () => {
    const story = createStoryDetails({
      currentScene: { key: "station", characterIds: ["role-1"] },
      cgGallery: [
        { id: "old", storyId: "story-1", kind: "cg", visualType: "character", sceneKey: "street", status: "ready", path: "old.png", prompt: "", sourceTurnId: null, sequence: 2, errorCode: null, createdAt: "", updatedAt: "" },
        { id: "current", storyId: "story-1", kind: "cg", visualType: "scene", sceneKey: "station", status: "ready", path: "current.png", prompt: "", sourceTurnId: null, sequence: 1, errorCode: null, createdAt: "", updatedAt: "" },
      ],
    });

    assert.equal(selectActiveStoryVisualResource(story)?.id, "current");
    assert.equal(isStoryRoleInCurrentScene(story), true);
  });
});
