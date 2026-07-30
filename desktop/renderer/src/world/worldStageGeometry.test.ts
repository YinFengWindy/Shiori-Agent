import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  coverWorldStage,
  fitWorldStage,
  placeWorldCharacter,
  worldStageSafeArea,
  worldStageSize,
} from "./worldStageGeometry";

describe("worldStageGeometry", () => {
  it("keeps the 1920x1080 logical stage centered at required viewport sizes", () => {
    assert.deepEqual(fitWorldStage(1920, 1080), {
      scale: 1,
      offsetX: 0,
      offsetY: 0,
      renderedWidth: 1920,
      renderedHeight: 1080,
    });
    assert.deepEqual(fitWorldStage(1280, 720), {
      scale: 2 / 3,
      offsetX: 0,
      offsetY: 0,
      renderedWidth: 1280,
      renderedHeight: 720,
    });
    const compact = fitWorldStage(1024, 640);
    assert.equal(compact.renderedWidth, 1024);
    assert.equal(compact.offsetY, 32);
    const ultrawide = fitWorldStage(2560, 1080);
    assert.equal(ultrawide.renderedHeight, 1080);
    assert.equal(ultrawide.offsetX, 320);
  });

  it("covers the logical stage with centered source cropping", () => {
    assert.deepEqual(coverWorldStage(1920, 1200), {
      x: 0,
      y: -60,
      width: 1920,
      height: 1200,
      scale: 1,
    });
    const portrait = coverWorldStage(1080, 1920);
    assert.equal(portrait.height, 1920 * (1920 / 1080));
    assert.equal(portrait.x, 0);
    assert.ok(portrait.y < 0);
  });

  it("maps normalized character slots to one stable safe-area baseline", () => {
    assert.deepEqual(worldStageSize, { width: 1920, height: 1080 });
    assert.deepEqual(worldStageSafeArea, { x: 160, y: 90, width: 1600, height: 900 });
    assert.deepEqual(placeWorldCharacter(0.5, 1200), { x: 960, y: 990, scale: 0.75 });
    assert.equal(placeWorldCharacter(-1, 900).x, 160);
    assert.equal(placeWorldCharacter(2, 900).x, 1760);
  });
});
