/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { clampChatImageZoom, getNextChatImageZoom } from "./chatImageLightboxState";

describe("clampChatImageZoom", () => {
  it("keeps the fully visible baseline zoom as the minimum", () => {
    assert.equal(clampChatImageZoom(0.6), 1);
  });

  it("caps zoom to the supported upper bound", () => {
    assert.equal(clampChatImageZoom(6), 4);
  });
});

describe("getNextChatImageZoom", () => {
  it("zooms in when the wheel scrolls upward", () => {
    assert.equal(getNextChatImageZoom(1, -100), 1.2);
  });

  it("zooms out when the wheel scrolls downward", () => {
    assert.equal(getNextChatImageZoom(1.4, 100), 1.2);
  });

  it("stops zooming out once the image is fully visible", () => {
    assert.equal(getNextChatImageZoom(1, 100), 1);
  });
});
