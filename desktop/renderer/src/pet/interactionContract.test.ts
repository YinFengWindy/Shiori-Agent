import assert from "node:assert/strict";
import test from "node:test";
import { petDragState, petHoverState } from "./interactionContract";

test("Codex pet interactions use jumping on hover and a four-pixel directional threshold", () => {
  assert.equal(petHoverState, "jumping");
  assert.equal(petDragState(120, 119), null);
  assert.equal(petDragState(120, 116), "running-left");
  assert.equal(petDragState(120, 124), "running-right");
});
