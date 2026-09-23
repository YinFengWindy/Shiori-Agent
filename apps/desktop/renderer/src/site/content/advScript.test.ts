/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ADV_EXIT_CHOICE_ID } from "../adv/advModel";
import { ADV_SCRIPT } from "./advScript";

const MAX_LINE_LENGTH = 40;

describe("ADV_SCRIPT", () => {
  it("offers the six feature topics in menu order", () => {
    assert.deepEqual(
      ADV_SCRIPT.topics.map((topic) => topic.label),
      ["聊天与多端", "角色与记忆", "生图", "故事模式", "桌宠", "插件"],
    );
    assert.equal(ADV_SCRIPT.exit.label, "没什么想问的了");
  });

  it("keeps the opening at 4–6 lines and each topic at 3–5 lines", () => {
    assert.ok(ADV_SCRIPT.opening.lines.length >= 4 && ADV_SCRIPT.opening.lines.length <= 6);
    for (const topic of ADV_SCRIPT.topics) {
      assert.ok(topic.lines.length >= 3 && topic.lines.length <= 5, topic.id);
    }
    assert.ok(ADV_SCRIPT.exit.lines.length >= 1);
  });

  it("keeps every line short enough for the dialogue box", () => {
    const lines = [
      ...ADV_SCRIPT.opening.lines,
      ...ADV_SCRIPT.topics.flatMap((topic) => topic.lines),
      ...ADV_SCRIPT.exit.lines,
      ADV_SCRIPT.choicePrompt.first,
      ADV_SCRIPT.choicePrompt.again,
    ];
    for (const line of lines) {
      assert.ok(line.length > 0 && line.length <= MAX_LINE_LENGTH, line);
    }
  });

  it("uses unique topic ids that never collide with the exit choice", () => {
    const ids = ADV_SCRIPT.topics.map((topic) => topic.id);
    assert.equal(new Set(ids).size, ids.length);
    assert.ok(!ids.includes(ADV_EXIT_CHOICE_ID));
  });

  it("switches art away from the opening for every topic", () => {
    for (const topic of ADV_SCRIPT.topics) {
      assert.notEqual(topic.art, ADV_SCRIPT.opening.art, topic.id);
    }
  });
});
