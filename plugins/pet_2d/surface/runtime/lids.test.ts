import assert from "node:assert/strict";
import test from "node:test";
import { lidLineMesh } from "./lids";
import type { EyeAnchor, Layer, Lid } from "./model";

const owner: Layer = { name: "eyelash", x: 0, y: 0, w: 40, h: 20, z: 0, depth: 1, group: "head", phys: null, fade: "eyeOpen", side: "L", image: "eye", opacity: 1, visible: true, synthetic: false };
const eye: EyeAnchor = { x0: 0, x1: 40, y0: 0, y1: 20, icx: 20, icy: 10, closeX: 20, closeY: 15, angle: 0 };
const lid: Lid = { side: "L", scale: 20, low: -20, high: 20, lower: [0, 0, 0], edge: [-10, 0, 0], smile: [-10, 0, 0], rise: 10, opening: 10, band: Array(65).fill(1), weight: 1, colour: [20, 20, 20], lashes: [], skin: null };
test("baked lid span cannot allocate a contour whose Uint16 indices would wrap", () => {
  assert.throws(() => lidLineMesh(owner, { ...lid, low: -10_000, high: 10_000 }, eye), /顶点预算|索引/);
});
test("a contour with safe indices still rejects an oversized generated texture", () => {
  assert.throws(() => lidLineMesh(owner, { ...lid, low: 0, high: 2048 }, eye), /纹理预算/);
});
