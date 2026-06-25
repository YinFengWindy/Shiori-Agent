/// <reference types="node" />

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { toFileUrl } from "./format";

describe("toFileUrl", () => {
  it("encodes windows paths as asset urls", () => {
    assert.equal(
      toFileUrl("C:\\Users\\yufeng\\My Avatars\\头像 #1.png"),
      "mira-asset://local?path=C%3A%5CUsers%5Cyufeng%5CMy%20Avatars%5C%E5%A4%B4%E5%83%8F%20%231.png",
    );
  });

  it("encodes posix paths as asset urls", () => {
    assert.equal(
      toFileUrl("/Users/yufeng/My Avatars/头像 #1.png"),
      "mira-asset://local?path=%2FUsers%2Fyufeng%2FMy%20Avatars%2F%E5%A4%B4%E5%83%8F%20%231.png",
    );
  });
});
