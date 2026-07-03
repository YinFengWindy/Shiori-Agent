/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { getLocalAssetMimeType } from "./assetMime";

describe("getLocalAssetMimeType", () => {
  it("returns markdown MIME types for .md files", () => {
    assert.equal(getLocalAssetMimeType("D:\\files\\README.md"), "text/markdown; charset=utf-8");
  });

  it("returns plain text MIME types for .txt files", () => {
    assert.equal(getLocalAssetMimeType("D:\\files\\notes.txt"), "text/plain; charset=utf-8");
  });
});
