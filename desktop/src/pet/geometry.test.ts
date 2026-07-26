import assert from "node:assert/strict";
import test from "node:test";
import { resolveDesktopPetBubbleLayout } from "./geometry.js";

const workArea = { x: 0, y: 0, width: 1920, height: 1080 };

test("desktop pet places a full bubble below when it fits", () => {
  assert.deepEqual(
    resolveDesktopPetBubbleLayout({ x: 1200, y: 300 }, workArea, 160),
    { placement: "below", height: 160 },
  );
});

test("desktop pet flips the full bubble above near the display bottom", () => {
  assert.deepEqual(
    resolveDesktopPetBubbleLayout({ x: 1200, y: 800 }, workArea, 160),
    { placement: "above", height: 160 },
  );
});

test("desktop pet constrains an oversized reply to the selected display side", () => {
  assert.deepEqual(
    resolveDesktopPetBubbleLayout({ x: 1200, y: 500 }, workArea, 2_000),
    { placement: "above", height: 494 },
  );
});
