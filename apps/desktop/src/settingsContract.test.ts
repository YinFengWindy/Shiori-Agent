import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { compactionRetainedTurnsError, desktopSettingsDefaults, modelCapacityError, modelCapacityErrors, summaryTokenLimitError } from "./settingsContract.js";

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

describe("modelCapacityError", () => {
  it("keeps an empty window saveable and accepts a threshold below the window", () => {
    assert.equal(modelCapacityError({ modelContextWindow: null, modelAutoCompactTokenLimit: null }), null);
    assert.equal(modelCapacityError({ modelContextWindow: 128000, modelAutoCompactTokenLimit: 100000 }), null);
    assert.equal(modelCapacityError({ modelContextWindow: null, modelAutoCompactTokenLimit: 1000 }), null);
  });

  it("names the reason a threshold at or beyond the window, or not positive, is rejected", () => {
    assert.equal(modelCapacityError({ modelContextWindow: 128000, modelAutoCompactTokenLimit: 128000 }), "自动压缩阈值必须小于上下文窗口");
    assert.equal(modelCapacityError({ modelContextWindow: null, modelAutoCompactTokenLimit: 0 }), "自动压缩阈值必须是正整数");
    assert.equal(modelCapacityError({ modelContextWindow: 128000, modelAutoCompactTokenLimit: 0 }), "自动压缩阈值必须是正整数");
    assert.equal(modelCapacityError({ modelContextWindow: 0 }), "上下文窗口必须是正整数");
    assert.deepEqual(modelCapacityErrors({ modelContextWindow: 1.5, modelAutoCompactTokenLimit: 1000 }), { modelContextWindow: "上下文窗口必须是正整数" });
  });
});


describe("summaryTokenLimitError", () => {
  it("accepts old settings and positive integer limits", () => {
    assert.equal(desktopSettingsDefaults.summaryTokenLimit, 2000);
    for (const value of [undefined, 1, 2000, 4000]) assert.equal(summaryTokenLimitError(value), null);
  });
  it("rejects malformed, fractional, unsafe and nonpositive limits", () => {
    for (const value of [null, "2000", true, 0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY, Number.MAX_SAFE_INTEGER + 1]) {
      assert.equal(summaryTokenLimitError(value), "工作摘要 token 上限必须是正整数");
    }
  });
});
