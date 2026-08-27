/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  PreloadLocalAssetCache,
  unavailableLocalAssetUrl,
} from "./preloadLocalAssetCache";

describe("PreloadLocalAssetCache", () => {
  it("caches transported references before returning the original value", () => {
    const cache = new PreloadLocalAssetCache();
    const value = { records: ["record-1"] };

    const result = cache.consume({
      value,
      assets: [{
        path: "C:\\workspace\\avatar.png",
        url: "shiori-asset://local/avatar-token",
        kind: "image",
      }],
    });

    assert.equal(result, value);
    assert.equal(cache.resolve("C:\\workspace\\avatar.png"), "shiori-asset://local/avatar-token");
  });

  it("uses the latest transported token for an existing path", () => {
    const cache = new PreloadLocalAssetCache();
    const path = "C:\\workspace\\note.md";
    cache.consume({
      value: undefined,
      assets: [{ path, url: "shiori-asset://local/first-token", kind: "document" }],
    });

    cache.consume({
      value: undefined,
      assets: [{ path, url: "shiori-asset://local/second-token", kind: "document" }],
    });

    assert.equal(cache.resolve(path), "shiori-asset://local/second-token");
  });

  it("returns a fixed non-sensitive URL for unknown paths", () => {
    const cache = new PreloadLocalAssetCache();
    const unknownPath = "C:\\private\\secret.png";

    assert.equal(cache.resolve(unknownPath), unavailableLocalAssetUrl);
    assert.equal(unavailableLocalAssetUrl, "shiori-asset://local/unavailable");
    assert.doesNotMatch(cache.resolve(unknownPath), /private|secret/i);
  });

  it("does not retain legacy path URLs", () => {
    const cache = new PreloadLocalAssetCache();
    const path = "C:\\private\\secret.png";
    cache.consume({
      value: undefined,
      assets: [{
        path,
        url: `shiori-asset://local?path=${encodeURIComponent(path)}`,
        kind: "image",
      }],
    });

    assert.equal(cache.resolve(path), unavailableLocalAssetUrl);
  });

  it("does not retain URLs from obsolete asset schemes", () => {
    const cache = new PreloadLocalAssetCache();
    const path = "C:\\workspace\\avatar.png";
    cache.consume({
      value: undefined,
      assets: [{ path, url: "legacy-asset://local/avatar-token", kind: "image" }],
    });

    assert.equal(cache.resolve(path), unavailableLocalAssetUrl);
  });
});
