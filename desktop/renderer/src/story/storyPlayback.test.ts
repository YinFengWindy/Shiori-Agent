/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { advanceStoryPlayback, createStoryPlaybackState, getNextStoryBeat, getPresentedStoryBeat, hasUnpresentedStoryBeats, syncStoryPlaybackState } from "./storyPlayback";
import { createStoryBeat, createStoryDetails } from "./testFixtures";

describe("storyPlayback", () => {
  it("starts existing history at the latest committed beat", () => {
    const story = createStoryDetails({ beats: [
      createStoryBeat({ id: "beat-1", sequence: 1, text: "第一段" }),
      createStoryBeat({ id: "beat-2", sequence: 2, text: "第二段" }),
    ] });
    const state = createStoryPlaybackState(story);

    assert.equal(getPresentedStoryBeat(story, state)?.id, "beat-2");
    assert.equal(getNextStoryBeat(story, state), null);
  });

  it("presents only the first beat of a newly committed batch", () => {
    const initialStory = createStoryDetails({ beats: [createStoryBeat()] });
    const nextStory = createStoryDetails({ revision: 2, beats: [
      createStoryBeat(),
      createStoryBeat({ id: "beat-2", sequence: 2, turnId: "turn-2", text: "第二段" }),
      createStoryBeat({ id: "beat-3", sequence: 3, turnId: "turn-2", text: "第三段" }),
    ] });
    const state = syncStoryPlaybackState(createStoryPlaybackState(initialStory), nextStory);

    assert.equal(getPresentedStoryBeat(nextStory, state)?.id, "beat-2");
    assert.equal(getNextStoryBeat(nextStory, state)?.id, "beat-3");
    assert.equal(hasUnpresentedStoryBeats(nextStory, state), true);
  });

  it("advances one beat at a time and does not jump to the end", () => {
    const initialStory = createStoryDetails({ beats: [createStoryBeat()] });
    const nextStory = createStoryDetails({ beats: [
      createStoryBeat(),
      createStoryBeat({ id: "beat-2", sequence: 2, turnId: "turn-2" }),
      createStoryBeat({ id: "beat-3", sequence: 3, turnId: "turn-2" }),
    ] });
    const firstState = syncStoryPlaybackState(createStoryPlaybackState(initialStory), nextStory);
    const secondState = advanceStoryPlayback(nextStory, firstState);

    assert.equal(getPresentedStoryBeat(nextStory, secondState)?.id, "beat-3");
    assert.equal(getNextStoryBeat(nextStory, secondState), null);
    assert.equal(hasUnpresentedStoryBeats(nextStory, secondState), false);
  });

  it("does not auto-advance when later events add another beat to the same turn", () => {
    const initialStory = createStoryDetails({ beats: [createStoryBeat()] });
    const firstStory = createStoryDetails({ revision: 2, beats: [
      createStoryBeat(),
      createStoryBeat({ id: "beat-2", sequence: 2, turnId: "turn-2" }),
    ] });
    const secondStory = createStoryDetails({ revision: 3, beats: [
      createStoryBeat(),
      createStoryBeat({ id: "beat-2", sequence: 2, turnId: "turn-2" }),
      createStoryBeat({ id: "beat-3", sequence: 3, turnId: "turn-2" }),
    ] });
    const firstState = syncStoryPlaybackState(createStoryPlaybackState(initialStory), firstStory);
    const secondState = syncStoryPlaybackState(firstState, secondStory);

    assert.equal(getPresentedStoryBeat(secondStory, secondState)?.id, "beat-2");
    assert.equal(getNextStoryBeat(secondStory, secondState)?.id, "beat-3");
  });

  it("keeps player input unavailable while a later beat is waiting", () => {
    const initialStory = createStoryDetails({ beats: [createStoryBeat()] });
    const nextStory = createStoryDetails({ beats: [
      createStoryBeat(),
      createStoryBeat({ id: "beat-2", sequence: 2, turnId: "turn-2" }),
      createStoryBeat({ id: "beat-3", sequence: 3, turnId: "turn-2" }),
    ] });
    const state = syncStoryPlaybackState(createStoryPlaybackState(initialStory), nextStory);

    assert.equal(hasUnpresentedStoryBeats(nextStory, state), true);
    assert.equal(getPresentedStoryBeat(nextStory, state)?.id, "beat-2");
    assert.equal(getNextStoryBeat(nextStory, state)?.id, "beat-3");
  });
});
