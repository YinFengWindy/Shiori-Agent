import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { maxWorldTextureDimension } from "./pixiWorldAssetLoader";
import { worldStageLayerNames } from "./pixiWorldPresentationRenderer";

describe("PixiWorldPresentationRenderer", () => {
  it("keeps the required stage layer ordering explicit", () => {
    assert.deepEqual(worldStageLayerNames, [
      "BackgroundLayer",
      "CharacterLayer",
      "CgLayer",
      "AtmosphereLayer",
      "TransitionLayer",
    ]);
    assert.equal(maxWorldTextureDimension, 4096);
  });
});
