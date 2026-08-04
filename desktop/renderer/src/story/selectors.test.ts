/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { canShowStoryInput, canSubmitStoryInput, getStoryStatusLabel, mergeStoryBeats, replaceStorySummary } from "./selectors";
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
});
