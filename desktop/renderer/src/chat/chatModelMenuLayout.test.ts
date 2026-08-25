import assert from "node:assert/strict";
import test from "node:test";
import { getChatModelMenuPosition } from "./chatModelMenuLayout";

test("anchors the menu bottom above the model button", () => {
  assert.deepEqual(
    getChatModelMenuPosition({ left: 24, top: 300 }, 500),
    { left: 24, bottom: 204 },
  );
});
