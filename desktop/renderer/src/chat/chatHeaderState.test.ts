/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolveChatHeaderTitle } from "./chatHeaderState";

describe("resolveChatHeaderTitle", () => {
  it("returns the empty-state title when no role is active", () => {
    assert.equal(resolveChatHeaderTitle({
      activeRoleId: "",
      activeRoleName: null,
      sending: false,
      sendingRoleId: "",
    }), "选择一个角色");
  });

  it("keeps the active role name when another role is sending", () => {
    assert.equal(resolveChatHeaderTitle({
      activeRoleId: "role-b",
      activeRoleName: "Role B",
      sending: true,
      sendingRoleId: "role-a",
    }), "Role B");
  });

  it("shows the typing title only for the role that is currently sending", () => {
    assert.equal(resolveChatHeaderTitle({
      activeRoleId: "role-a",
      activeRoleName: "Role A",
      sending: true,
      sendingRoleId: "role-a",
    }), "正在输入中...");
  });
});
