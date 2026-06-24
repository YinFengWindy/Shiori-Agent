/// <reference types="node" />

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { toFileUrl } from "./format";

describe("toFileUrl", () => {
  it("encodes windows paths segment by segment", () => {
    assert.equal(
      toFileUrl("C:\\Users\\yufeng\\My Avatars\\头像 #1.png"),
      "file://C:/Users/yufeng/My%20Avatars/%E5%A4%B4%E5%83%8F%20%231.png",
    );
  });

  it("encodes posix paths segment by segment", () => {
    assert.equal(
      toFileUrl("/Users/yufeng/My Avatars/头像 #1.png"),
      "file:///Users/yufeng/My%20Avatars/%E5%A4%B4%E5%83%8F%20%231.png",
    );
  });
});
