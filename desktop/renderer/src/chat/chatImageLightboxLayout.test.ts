/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { clampChatImageOffset, fitChatImageToStage } from "./chatImageLightboxLayout";

describe("fitChatImageToStage", () => {
  it("fits the image within the stage while preserving aspect ratio", () => {
    assert.deepEqual(
      fitChatImageToStage({ width: 1000, height: 800 }, { width: 1600, height: 900 }),
      { width: 1000, height: 562.5 },
    );
  });
});

describe("clampChatImageOffset", () => {
  it("allows dragging within the spare margin when the fitted image is smaller than the stage", () => {
    assert.deepEqual(
      clampChatImageOffset(
        { x: 999, y: -999 },
        { width: 1000, height: 800 },
        { width: 1000, height: 562.5 },
        1,
      ),
      { x: 0, y: -118.75 },
    );
  });

  it("prevents zoomed images from being dragged beyond the visible recovery range", () => {
    assert.deepEqual(
      clampChatImageOffset(
        { x: 999, y: -999 },
        { width: 1000, height: 800 },
        { width: 1000, height: 562.5 },
        2,
      ),
      { x: 500, y: -162.5 },
    );
  });
});
