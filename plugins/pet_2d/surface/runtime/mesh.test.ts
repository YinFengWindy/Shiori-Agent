import assert from "node:assert/strict";
import test from "node:test";
import { gridIndices, imageMesh } from "./mesh";
import type { Layer } from "./model";

test("indices retain the last vertex at the mesh limit and reject overflow instead of wrapping", () => {
  assert.equal(gridIndices(250, 260).at(-1), 64_999);
  assert.throws(() => gridIndices(20_001, 4), /顶点预算|索引/);
});
test("grid and image dimensions reject fractional or nonfinite allocation sizes", () => {
  assert.throws(() => gridIndices(2.5, 3), /尺寸/);
  const layer: Layer = { name: "face", x: 0, y: 0, w: Infinity, h: 10, z: 0, depth: 1, group: "head", phys: null, fade: null, side: null, image: "face", opacity: 1, visible: true, synthetic: false };
  assert.throws(() => imageMesh(layer), /尺寸/);
});
