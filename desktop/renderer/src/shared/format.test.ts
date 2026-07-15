/// <reference types="node" />

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { toFileUrl } from "./format";

describe("toFileUrl", () => {
  it("fails closed when the desktop preload boundary is unavailable", () => {
    assert.equal(
      toFileUrl("C:\\private\\secret.png"),
      "mira-asset://local/unavailable",
    );
  });

  it("returns the opaque token URL from the desktop resolver unchanged", () => {
    const absolutePath = "C:\\Users\\yufeng\\My Avatars\\头像 #1.png";
    const opaqueUrl = "mira-asset://local/token-2fR9dQ";
    let resolvedPath = "";

    const result = toFileUrl(absolutePath, (path) => {
      resolvedPath = path;
      return opaqueUrl;
    });

    assert.equal(resolvedPath, absolutePath);
    assert.equal(result, opaqueUrl);
    assert.equal(result.includes(absolutePath), false);
  });

  it("does not encode or embed POSIX paths before resolving them", () => {
    const absolutePath = "/Users/yufeng/My Avatars/头像 #1.png";
    const opaqueUrl = "mira-asset://local/token-k8Lm3P";

    const result = toFileUrl(absolutePath, (path) => {
      assert.equal(path, absolutePath);
      assert.equal(path.includes("%2F"), false);
      return opaqueUrl;
    });

    assert.equal(result, opaqueUrl);
    assert.equal(result.includes(absolutePath), false);
  });
});
