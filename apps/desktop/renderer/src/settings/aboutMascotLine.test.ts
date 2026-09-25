/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { aboutUpdateLines } from "../shared/mascot/mascotLines";
import { aboutLineForPhaseChange } from "./aboutMascotLine";

describe("aboutLineForPhaseChange", () => {
  it("announces a found update however the page learns of it", () => {
    assert.equal(aboutLineForPhaseChange(undefined, "downloaded"), aboutUpdateLines.available);
    assert.equal(aboutLineForPhaseChange("checking", "downloading"), aboutUpdateLines.available);
    // Downloading -> downloaded is the same news.
    assert.equal(aboutLineForPhaseChange("downloading", "downloaded"), null);
  });

  it("says 已经是最新的啦 only when a check it saw finishes", () => {
    assert.equal(aboutLineForPhaseChange("checking", "current"), aboutUpdateLines.current);
    assert.equal(aboutLineForPhaseChange("idle", "current"), aboutUpdateLines.current);
    // Reopening 关于 after an earlier check keeps the random opening line.
    assert.equal(aboutLineForPhaseChange(undefined, "current"), null);
  });

  it("worries when the update fails, also on opening the page after a failure", () => {
    assert.equal(aboutLineForPhaseChange("checking", "error"), aboutUpdateLines.failed);
    assert.equal(aboutLineForPhaseChange(undefined, "error"), aboutUpdateLines.failed);
  });

  it("keeps her line for everything else", () => {
    assert.equal(aboutLineForPhaseChange(undefined, "idle"), null);
    assert.equal(aboutLineForPhaseChange("idle", "checking"), null);
    assert.equal(aboutLineForPhaseChange("current", "current"), null);
  });
});
