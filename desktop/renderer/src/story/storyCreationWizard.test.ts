/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createInitialStoryCreationInput, isCreationStepComplete } from "./storyCreationWizard";

describe("storyCreationWizard", () => {
  it("requires each Story create field before creation can start", () => {
    const input = createInitialStoryCreationInput();
    assert.equal(isCreationStepComplete("role", input), false);
    assert.equal(isCreationStepComplete("player", input), false);
    assert.equal(isCreationStepComplete("review", input), false);

    input.roleId = "role-1";
    input.title = "雨港";
    input.background = "潮汐带回名字";
    input.startsAt = "2026-08-02T10:00";
    input.playerProfile = { displayName: "岚", identity: "抄写员", appearance: "短发" };

    assert.equal(isCreationStepComplete("role", input), true);
    assert.equal(isCreationStepComplete("setting", input), true);
    assert.equal(isCreationStepComplete("player", input), true);
    assert.equal(isCreationStepComplete("review", input), true);
  });
});
