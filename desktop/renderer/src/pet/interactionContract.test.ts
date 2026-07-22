import assert from "node:assert/strict";
import test from "node:test";
import { petDragState, petHoverState } from "./interactionContract";

test("Codex pet pointer interactions use the documented hover and directional rows", () => {
  assert.equal(petHoverState, "waving");
  assert.equal(petDragState(120, 119), "running-left");
  assert.equal(petDragState(120, 121), "running-right");
  assert.equal(petDragState(120, 120), null);
});
