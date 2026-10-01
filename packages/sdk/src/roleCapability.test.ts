import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { roleToggleStatus } from "./roleCapability";

describe("roleToggleStatus", () => {
  it("maps the switch and lets an unavailable reason win", () => {
    assert.deepEqual(roleToggleStatus(true), { label: "已启用", tone: "on" });
    assert.deepEqual(roleToggleStatus(false), { label: "未启用", tone: "off" });
    assert.deepEqual(roleToggleStatus(true, "未配置桌宠"), { label: "未配置桌宠", tone: "off" });
  });
});
