import assert from "node:assert/strict";
import test from "node:test";
import { decodeFloat32, parseAvatarModel } from "./model";

function fixture() {
  const eye = { x0: 0, x1: 10, y0: 0, y1: 10, icx: 5, icy: 5, closeX: 6, closeY: 8, angleRadians: 0.1 };
  const anchors = { face: { x0: 0, x1: 30, y0: 0, y1: 30, cx: 15, cy: 15 }, neckPivot: { cx: 15, cy: 40 }, bodyPivot: { cx: 15, cy: 64 }, mouth: { cx: 15, cy: 25 }, eyeL: eye, eyeR: { ...eye, closeX: 24 }, faceScale: 0.5 };
  const layer = { name: "mouth_open", x: 7, y: 8, w: 10, h: 10, z: 0, depth: 1, group: "head", image: { file: "layers/000.webp" } };
  return { manifest: { schema: "prelulu-avatar-package/v1" }, binding: { schema: "prelulu-avatar-binding/v1", canvas: { width: 64, height: 64 } }, rig: { schema: "prelulu-rig-bundle/v1", rig: { canvas: { w: 64, h: 64 }, layers: [{ ...layer, x: 99 }] } }, baked: {
    schema: "prelulu-rig-bake/v1", prepared: { version: "prepared-v1-78b039a0f17fac16", layers: [layer], anchors },
    hair: { version: "hair-v1-2de9459fc64e7fc1", layers: [] }, lids: { version: "lids-v1-5f0c2e9a71d4b836", eyes: [] },
    mouth: { version: "mouth-v1-49795064767624ca", closed: 0, choice: { renderer: "parametric" }, parametric: { x: 10, y: 20, w: 10, h: 10, fit: { origin: { x: 14.25, y: 24.5 }, angle: 0.1, style: { halfWidth: 5, lineWidth: 1, restCurve: -0.1, openHeight: 1, ink: [1, 2, 3], cavity: [4, 5, 6], tongue: [7, 8, 9], teeth: [250, 250, 250] } } }, articulation: { openPx: 3, reach: { widenPx: 1, liftPx: 2 } } },
  }, images: [{ file: "rig/layers/000.webp", url: "shiori-asset://authorized" }] };
}
test("prepared coordinates, corrected eye axis and measured mouth placement survive parsing", () => {
  const model = parseAvatarModel(fixture());
  assert.equal(model.layers[0].x, 7); assert.equal(model.anchors.eyeL.closeX, 6); assert.equal(model.anchors.eyeL.angle, 0.1);
  assert.deepEqual(model.mouth.origin, { x: 14.25, y: 24.5 }); assert.deepEqual(model.mouth.reach, { widenPx: 1, liftPx: 2 });
});
test("unsupported bakes and ungranted image references fail before rendering", () => {
  const model = fixture(); model.baked.prepared.version = "prepared-v1-other";
  assert.throws(() => parseAvatarModel(model), /prepared/);
  assert.throws(() => parseAvatarModel({ ...fixture(), images: [] }), /缺少模型图片/);
});
test("hair buffers use little endian and reject truncation or nonfinite vertex data", () => {
  const buffer = new ArrayBuffer(8), view = new DataView(buffer); view.setFloat32(0, 1.25, true); view.setFloat32(4, -2.5, true);
  const encoded = Buffer.from(buffer).toString("base64"); assert.deepEqual([...decodeFloat32(encoded, 2)], [1.25, -2.5]);
  assert.throws(() => decodeFloat32(encoded, 3), /长度/);
  view.setFloat32(4, NaN, true); assert.throws(() => decodeFloat32(Buffer.from(buffer).toString("base64"), 2), /数值/);
});
