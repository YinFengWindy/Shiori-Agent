/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { getStoryBeatPresentationFragments } from "./storyBeatPresentation";
import { createStoryBeat } from "./testFixtures";

describe("getStoryBeatPresentationFragments", () => {
  it("keeps pure dialogue as one dialogue fragment", () => {
    const fragments = getStoryBeatPresentationFragments(createStoryBeat({ kind: "dialogue", text: "你来了。" }));

    assert.deepEqual(fragments, [{ kind: "dialogue", text: "你来了。" }]);
  });

  it("splits narration around quoted dialogue", () => {
    const fragments = getStoryBeatPresentationFragments(createStoryBeat({ kind: "dialogue", text: "她抬眼看向你：\"你来了。\"" }));

    assert.deepEqual(fragments, [
      { kind: "narration", text: "她抬眼看向你：" },
      { kind: "dialogue", text: "\"你来了。\"" },
    ]);
  });

  it("presents action and narration beats as narration", () => {
    assert.deepEqual(getStoryBeatPresentationFragments(createStoryBeat({ kind: "narration", text: "雨停了。" })), [{ kind: "narration", text: "雨停了。" }]);
    assert.deepEqual(getStoryBeatPresentationFragments(createStoryBeat({ kind: "action", text: "她走近窗边。" })), [{ kind: "narration", text: "她走近窗边。" }]);
  });
});
