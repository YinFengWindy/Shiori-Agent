import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { fitChatMessageImage } from "./chatMessageImageLayout";

describe("fitChatMessageImage", () => {
  it("keeps small images at their intrinsic size", () => {
    assert.deepEqual(fitChatMessageImage({ width: 320, height: 180 }), { width: 320, height: 180 });
  });

  it("fits portrait images within both bounds", () => {
    assert.deepEqual(fitChatMessageImage({ width: 832, height: 1216 }), { width: 192, height: 280 });
  });

  it("returns zero size for invalid dimensions", () => {
    assert.deepEqual(fitChatMessageImage({ width: 0, height: 100 }), { width: 0, height: 0 });
  });
});
