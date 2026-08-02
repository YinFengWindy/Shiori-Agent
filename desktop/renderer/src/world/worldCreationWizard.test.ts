/// <reference types="node" />
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createInitialWorldCreationInput, isCreationStepComplete } from "./worldCreationWizard";

describe("worldCreationWizard", () => {
  it("requires each preceding decision before the review can start a Story", () => {
    const input = createInitialWorldCreationInput("seed");
    assert.equal(isCreationStepComplete("role", input), false);
    assert.equal(isCreationStepComplete("review", input), false);

    input.selectedRoleIds = ["role-1"];
    input.name = "雨港";
    input.premise = "潮汐带回名字";
    input.firstOc = { name: "岚", identity: "抄写员", entryTime: "2026-08-02T10:00", entryLocation: "短发", primaryGoal: "" };

    assert.equal(isCreationStepComplete("role", input), true);
    assert.equal(isCreationStepComplete("setting", input), true);
    assert.equal(isCreationStepComplete("player", input), true);
    assert.equal(isCreationStepComplete("review", input), true);
  });
});
