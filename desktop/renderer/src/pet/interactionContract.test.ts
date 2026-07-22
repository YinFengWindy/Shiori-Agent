import assert from "node:assert/strict";
import test from "node:test";
import { hasPetDragMoved, petDragState, petHoverState } from "./interactionContract";

test("Codex pet interactions use jumping on hover and a four-pixel directional threshold", () => {
  assert.equal(petHoverState, "jumping");
  assert.equal(petDragState(120, 119), null);
  assert.equal(petDragState(120, 116), "running-left");
  assert.equal(petDragState(120, 124), "running-right");
});

test("Codex pet treats vertical movement as a drag without selecting a horizontal run row", () => {
  assert.equal(hasPetDragMoved(120, 160, 120, 163), false);
  assert.equal(hasPetDragMoved(120, 160, 120, 164), true);
  assert.equal(petDragState(120, 120), null);
});
