import assert from "node:assert/strict";
import test from "node:test";
import { constrainHair, createHairMotion, hairDisplacement, stepHair } from "./hair";
import type { HairPins } from "./model";

const pins: HairPins = { layer: 0, nx: 1, ny: 1, kind: "back", strands: [{ x: 0, rootY: 0, tipY: 10, attachY: 2, hang: 8, freedom: 1, restsOn: null }], rest: new Float32Array(8), weights: new Float32Array([1, 1, 1, 1]), freedom: new Float32Array([0, 1, 1, 1]), hang: new Float32Array([0, 8, 8, 8]), cap: new Float32Array([0, 2, 2, 2]), lo: new Float32Array([0, -3, -3, -3]), hi: new Float32Array([0, 1, 1, 1]) };
test("pinned roots stay fixed and travel respects directional and radial bounds", () => {
  assert.deepEqual(constrainHair(pins, 0, 100, 20), [0, 0]);
  const point = constrainHair(pins, 1, 100); assert.ok(point[0] <= 1); assert.ok(Math.hypot(...point) <= 2); assert.ok(point[1] < 0);
  const other = constrainHair(pins, 1, -100, 20); assert.ok(Math.hypot(...other) <= 2 + 1e-6);
});
test("reduced motion clears residual strand movement after a delayed frame", () => {
  const motion = createHairMotion(pins); stepHair(motion, 4, 5, 1, true);
  assert.ok(motion.every((strand) => Number.isFinite(strand.soft.offset)));
  stepHair(motion, 4.1, 0.1, 1, false);
  assert.deepEqual(hairDisplacement(pins, motion, 1), [0, 0]); assert.deepEqual(hairDisplacement(pins, motion, 0), [0, 0]);
});
