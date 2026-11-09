import assert from "node:assert/strict";
import test from "node:test";
import {
  isSamePetBubbleExtension,
  noPetBubble,
  petBubbleGap,
  petBubbleSurfaceExtension,
  resolvePetBubblePlacement,
} from "./bubbleExtension";

const workArea = { y: 0, height: 1080 };

test("a bubble that fits below the pet stays below it", () => {
  assert.deepEqual(
    resolvePetBubblePlacement(300, workArea, 160, 208),
    { placement: "below", height: 160 },
  );
});

test("a bubble flips above the pet near the display bottom", () => {
  assert.deepEqual(
    resolvePetBubblePlacement(800, workArea, 160, 208),
    { placement: "above", height: 160 },
  );
});

test("an oversized reply is constrained to the side with more room", () => {
  assert.deepEqual(
    resolvePetBubblePlacement(500, workArea, 2_000, 208),
    { placement: "above", height: 494 },
  );
});

test("no measured height means no bubble and no extension", () => {
  assert.deepEqual(resolvePetBubblePlacement(500, workArea, 0, 208), noPetBubble);
  assert.deepEqual(petBubbleSurfaceExtension(noPetBubble), { side: "below", size: 0 });
});

test("a non-finite measurement degrades to no bubble instead of NaN window bounds", () => {
  assert.deepEqual(resolvePetBubblePlacement(500, workArea, Number.NaN, 208), noPetBubble);
  assert.deepEqual(resolvePetBubblePlacement(500, workArea, Number.POSITIVE_INFINITY, 208), noPetBubble);
});

test("a fractional measurement is rounded up so the bubble is never clipped", () => {
  assert.deepEqual(
    resolvePetBubblePlacement(300, workArea, 72.1, 208),
    { placement: "below", height: 73 },
  );
});

test("the extension adds the sprite-to-bubble gap on the bubble's side", () => {
  assert.deepEqual(
    petBubbleSurfaceExtension({ placement: "above", height: 120 }),
    { side: "above", size: 120 + petBubbleGap },
  );
  assert.deepEqual(
    petBubbleSurfaceExtension({ placement: "below", height: 120 }),
    { side: "below", size: 120 + petBubbleGap },
  );
});

test("extension equality is what stops a resize feedback loop", () => {
  assert.equal(
    isSamePetBubbleExtension({ side: "above", size: 126 }, { side: "above", size: 126 }),
    true,
  );
  assert.equal(
    isSamePetBubbleExtension({ side: "above", size: 126 }, { side: "below", size: 126 }),
    false,
  );
  assert.equal(
    isSamePetBubbleExtension({ side: "below", size: 0 }, { side: "below", size: 126 }),
    false,
  );
});

test("a work area that does not start at the screen origin is respected", () => {
  // A taskbar-reserved strip at the top: y=200 leaves only 200-100-gap above.
  assert.deepEqual(
    resolvePetBubblePlacement(200, { y: 100, height: 400 }, 400, 208),
    { placement: "above", height: 94 },
  );
});
