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

  it("splits quoted dialogue even when the Director labels the mixed beat as narration", () => {
    const fragments = getStoryBeatPresentationFragments(createStoryBeat({
      kind: "narration",
      text: "她嘴上凶着，却伸手把你碗里凉掉的汤换成了自己手边那碗还温着的。玫粉色的眼睛低垂着，声音细得像抱怨：“……吃快点，凉了又该胃疼了。”",
    }));

    assert.deepEqual(fragments, [
      { kind: "narration", text: "她嘴上凶着，却伸手把你碗里凉掉的汤换成了自己手边那碗还温着的。玫粉色的眼睛低垂着，声音细得像抱怨：" },
      { kind: "dialogue", text: "“……吃快点，凉了又该胃疼了。”" },
    ]);
  });

  it("splits quoted dialogue after a colon with optional whitespace", () => {
    const fragments = getStoryBeatPresentationFragments(createStoryBeat({
      kind: "action",
      text: "她停顿了一下： \"别乱动。\"",
    }));

    assert.deepEqual(fragments, [
      { kind: "narration", text: "她停顿了一下：" },
      { kind: "dialogue", text: "\"别乱动。\"" },
    ]);
  });

  it("keeps every supported historical quote style and trailing narration", () => {
    const fragments = getStoryBeatPresentationFragments(createStoryBeat({
      kind: "narration",
      text: "她轻声说：「别担心。」随后替你关上窗。",
    }));

    assert.deepEqual(fragments, [
      { kind: "narration", text: "她轻声说：" },
      { kind: "dialogue", text: "「别担心。」" },
      { kind: "narration", text: "随后替你关上窗。" },
    ]);
  });

  it("keeps ordinary quoted text together when it is not introduced by a colon", () => {
    const fragments = getStoryBeatPresentationFragments(createStoryBeat({
      kind: "action",
      text: "她听到你这声撒娇般的\"啊——\"，动作明显一滞。",
    }));

    assert.deepEqual(fragments, [{
      kind: "narration",
      text: "她听到你这声撒娇般的\"啊——\"，动作明显一滞。",
    }]);
  });

  it("presents action and narration beats as narration", () => {
    assert.deepEqual(getStoryBeatPresentationFragments(createStoryBeat({ kind: "narration", text: "雨停了。" })), [{ kind: "narration", text: "雨停了。" }]);
    assert.deepEqual(getStoryBeatPresentationFragments(createStoryBeat({ kind: "action", text: "她走近窗边。" })), [{ kind: "narration", text: "她走近窗边。" }]);
  });
});
