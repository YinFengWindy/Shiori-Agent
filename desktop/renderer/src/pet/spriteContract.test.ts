import assert from "node:assert/strict";
import test from "node:test";
import { spriteAnimations, spriteFramePosition } from "./spriteContract";

test("Codex sprite contract maps every state to its documented atlas row", () => {
  assert.deepEqual(Object.values(spriteAnimations).map((item) => item.row), [0, 1, 2, 3, 4, 5, 6, 7, 8]);
  assert.deepEqual(Object.values(spriteAnimations).map((item) => item.frames), [6, 8, 8, 4, 5, 8, 6, 6, 6]);
});

test("sprite frame position wraps inside the active row", () => {
  assert.equal(spriteFramePosition("running-right", 8), "0px -208px");
  assert.equal(spriteFramePosition("review", -1), "-960px -1664px");
});
