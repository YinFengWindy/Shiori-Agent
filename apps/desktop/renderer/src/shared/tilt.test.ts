import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { canTilt, tiltFromPointer } from "./tilt";

const rect = { left: 100, top: 200, width: 200, height: 250 };

describe("tiltFromPointer", () => {
  it("sits flat with a centred glare at the centre", () => {
    assert.deepEqual(tiltFromPointer({ x: 200, y: 325 }, rect), { rotateX: 0, rotateY: 0, glareX: 0, highlightX: 50, highlightY: 50 });
  });

  it("leans the full angle at the corners, towards the pointer", () => {
    const topRight = tiltFromPointer({ x: 300, y: 200 }, rect, 8);
    assert.equal(topRight.rotateX, 8);
    assert.equal(topRight.rotateY, 8);
    const bottomLeft = tiltFromPointer({ x: 100, y: 450 }, rect, 8);
    assert.equal(bottomLeft.rotateX, -8);
    assert.equal(bottomLeft.rotateY, -8);
  });

  it("clamps a pointer outside the card to its edge", () => {
    const outside = tiltFromPointer({ x: 900, y: -40 }, rect, 8);
    assert.equal(outside.rotateY, 8);
    assert.equal(outside.rotateX, 8);
    assert.equal(outside.highlightX, 100);
    assert.equal(outside.highlightY, 0);
  });

  it("never exceeds the maximum", () => {
    for (const [x, y] of [[0, 0], [1000, 1000], [150, 260]] as const) {
      const frame = tiltFromPointer({ x, y }, rect, 8);
      assert.ok(Math.abs(frame.rotateX) <= 8 && Math.abs(frame.rotateY) <= 8);
    }
  });
});

describe("canTilt", () => {
  it("refuses touch and pen input", () => {
    assert.equal(canTilt("touch"), false);
    assert.equal(canTilt("pen"), false);
  });

  it("refuses when there is no window to ask (no hover capability known)", () => {
    assert.equal(canTilt("mouse"), false);
  });
});
