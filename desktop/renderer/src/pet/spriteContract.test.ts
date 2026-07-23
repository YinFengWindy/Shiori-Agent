import assert from "node:assert/strict";
import test from "node:test";
import {
  spriteActionLoopCount,
  spriteAnimations,
  spriteFrameDuration,
  spriteFramePosition,
  spriteIdleFrameDurationScale,
  spritePlaybackFrames,
} from "./spriteContract";

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

test("Codex sprite playback loops active rows three times then settles into a slow idle cycle", () => {
  const runningRight = spritePlaybackFrames("running-right");
  assert.equal(spriteActionLoopCount, 3);
  assert.equal(spriteIdleFrameDurationScale, 6);
  assert.equal(runningRight.length, 8 * spriteActionLoopCount + 6);
  assert.deepEqual(runningRight.slice(0, 8).map(({ state, frame, duration }) => ({ state, frame, duration })), [
    { state: "running-right", frame: 0, duration: 120 },
    { state: "running-right", frame: 1, duration: 120 },
    { state: "running-right", frame: 2, duration: 120 },
    { state: "running-right", frame: 3, duration: 120 },
    { state: "running-right", frame: 4, duration: 120 },
    { state: "running-right", frame: 5, duration: 120 },
    { state: "running-right", frame: 6, duration: 120 },
    { state: "running-right", frame: 7, duration: 220 },
  ]);
  assert.deepEqual(runningRight.slice(-2), [
    { state: "idle", frame: 4, duration: 840 },
    { state: "idle", frame: 5, duration: 1920 },
  ]);
  assert.equal(spriteFrameDuration("running-right", 7), 220);
});
