import assert from "node:assert/strict";
import test from "node:test";
import { desktopPetPositionFromCursor } from "./drag.js";

test("desktop pet drag follows the main-process cursor with the original pointer offset", () => {
  assert.deepEqual(
    desktopPetPositionFromCursor({ x: 640, y: 480 }, { x: 72, y: 104 }),
    { x: 568, y: 376 },
  );
});
