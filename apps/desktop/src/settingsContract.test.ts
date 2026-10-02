import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { compactionRetainedTurnsError, desktopSettingsDefaults } from "./settingsContract.js";

describe("compactionRetainedTurnsError", () => {
  it("accepts the default, zero and custom whole-turn retention", () => {
    assert.equal(desktopSettingsDefaults.compactionRetainedTurns, 2);
    for (const value of [undefined, 0, 2, 8]) assert.equal(compactionRetainedTurnsError(value), null);
  });

  it("rejects fractional, negative, unsafe and non-finite values consistently", () => {
    for (const value of [null, "2", true, {}, -1, 0.5, Number.MAX_SAFE_INTEGER + 1, Number.NaN, Number.POSITIVE_INFINITY]) {
      assert.equal(compactionRetainedTurnsError(value), "压缩后保留原文轮数必须是非负整数");
    }
  });
});
