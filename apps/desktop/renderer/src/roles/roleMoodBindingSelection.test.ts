/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { applyMoodToIllustration, getMoodForIllustration } from "./roleMoodBindingSelection";

describe("getMoodForIllustration", () => {
  it("finds the mapped mood for the selected illustration", () => {
    assert.equal(
      getMoodForIllustration("illustrations/happy.png", { 开心: "illustrations/happy.png", 平静: "illustrations/calm.png" }),
      "开心",
    );
  });

  it("returns an empty string when no mood owns the illustration", () => {
    assert.equal(
      getMoodForIllustration("illustrations/missing.png", { 开心: "illustrations/happy.png" }),
      "",
    );
  });
});

describe("applyMoodToIllustration", () => {
  it("assigns the selected illustration to the next mood", () => {
    assert.deepEqual(
      applyMoodToIllustration({ 平静: "illustrations/calm.png" }, "illustrations/happy.png", "开心"),
      { 平静: "illustrations/calm.png", 开心: "illustrations/happy.png" },
    );
  });

  it("moves the illustration away from the previous mood owner", () => {
    assert.deepEqual(
      applyMoodToIllustration({ 平静: "illustrations/shared.png", 开心: "illustrations/happy.png" }, "illustrations/shared.png", "警觉"),
      { 开心: "illustrations/happy.png", 警觉: "illustrations/shared.png" },
    );
  });

  it("clears the selected illustration mapping when the mood is blank", () => {
    assert.deepEqual(
      applyMoodToIllustration({ 平静: "illustrations/shared.png", 开心: "illustrations/happy.png" }, "illustrations/shared.png", " "),
      { 开心: "illustrations/happy.png" },
    );
  });
});
