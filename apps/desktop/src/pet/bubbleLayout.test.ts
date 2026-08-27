import assert from "node:assert/strict";
import test from "node:test";
import { DesktopPetBubbleLayout } from "./bubbleLayout.js";

const workArea = { x: 0, y: 0, width: 1920, height: 1080 };

test("bubble layout expands the window below the pet when the reply fits", () => {
  const layout = new DesktopPetBubbleLayout();
  assert.equal(layout.setMeasuredHeight(120), true);

  const bounds = layout.place({ x: 510, y: 300 }, workArea);

  assert.deepEqual(layout.layout, { placement: "below", height: 120 });
  assert.deepEqual(bounds, { x: 510, y: 300, width: 192, height: 334 });
});

test("bubble layout flips the window above the pet and recovers its anchor", () => {
  const layout = new DesktopPetBubbleLayout();
  layout.setMeasuredHeight(120);

  const bounds = layout.place({ x: 510, y: 800 }, workArea);

  assert.deepEqual(layout.layout, { placement: "above", height: 120 });
  assert.deepEqual(bounds, { x: 510, y: 674, width: 192, height: 334 });
  assert.deepEqual(layout.anchorFromWindow({ x: bounds.x, y: bounds.y }), { x: 510, y: 800 });
});

test("bubble layout ignores unchanged and invalid renderer measurements", () => {
  const layout = new DesktopPetBubbleLayout();

  assert.equal(layout.setMeasuredHeight(72.1), true);
  assert.equal(layout.setMeasuredHeight(73), false);
  assert.equal(layout.setMeasuredHeight(Number.NaN), false);
  layout.reset();
  assert.deepEqual(layout.layout, { placement: "below", height: 0 });
});
