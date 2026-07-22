import assert from "node:assert/strict";
import test from "node:test";
import { petDragState, petHoverState } from "./interactionContract";

test("Codex pet pointer interactions use the documented hover and directional rows", () => {
  assert.equal(petHoverState, "jumping");
  assert.equal(petDragState(120, 119), null);
  assert.equal(petDragState(120, 116), "running-left");
  assert.equal(petDragState(120, 124), "running-right");
  assert.equal(petDragState(120, 120), null);
});
