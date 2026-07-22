import assert from "node:assert/strict";
import test from "node:test";
import { spriteAnimations, spriteFrameDuration, spriteFramePosition } from "./spriteContract";

test("Codex sprite contract maps every state to its documented atlas row", () => {
  assert.deepEqual(Object.values(spriteAnimations).map((item) => item.row), [0, 1, 2, 3, 4, 5, 6, 7, 8]);
  assert.deepEqual(Object.values(spriteAnimations).map((item) => item.frames), [6, 8, 8, 4, 5, 8, 6, 6, 6]);
  assert.deepEqual(Object.values(spriteAnimations).map((item) => item.frameDurations), [
    [280, 110, 110, 140, 140, 320],
    [120, 120, 120, 120, 120, 120, 120, 220],
    [120, 120, 120, 120, 120, 120, 120, 220],
    [140, 140, 140, 280],
    [140, 140, 140, 140, 280],
    [140, 140, 140, 140, 140, 140, 140, 240],
    [150, 150, 150, 150, 150, 260],
    [120, 120, 120, 120, 120, 220],
    [150, 150, 150, 150, 150, 280],
  ]);
});

test("sprite frame position wraps inside the active row", () => {
  assert.equal(spriteFramePosition("running-right", 8), "0px -208px");
  assert.equal(spriteFramePosition("review", -1), "-960px -1664px");
});

test("sprite playback is slowed uniformly without changing the Codex frame cadence", () => {
  assert.equal(spriteFrameDuration("running-right", 0), 144);
  assert.equal(spriteFrameDuration("running-right", 7), 264);
});
