import assert from "node:assert/strict";
import test from "node:test";
import { getChatModelMenuPosition } from "./chatModelMenuLayout";

test("anchors the menu bottom above the model button", () => {
  assert.deepEqual(
    getChatModelMenuPosition({ left: 24, top: 300 }, { width: 1000, height: 500 }, 240),
    { left: 24, bottom: 204, maxHeight: 288 },
  );
});

test("keeps the menu inside a narrow window", () => {
  assert.equal(getChatModelMenuPosition({ left: 700, top: 300 }, { width: 800, height: 500 }, 240).left, 552);
});

test("limits the menu to the room above the button so it scrolls instead of overflowing", () => {
  assert.equal(getChatModelMenuPosition({ left: 24, top: 200 }, { width: 1000, height: 800 }, 240).maxHeight, 188);
});
