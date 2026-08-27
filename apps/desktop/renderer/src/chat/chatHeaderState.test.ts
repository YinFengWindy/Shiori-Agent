/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolveChatHeaderTitle, resolveVisibleChatSessionKey } from "./chatHeaderState";

describe("resolveChatHeaderTitle", () => {
  it("prefers the active role session key over the stale active session key during role switches", () => {
    assert.equal(resolveVisibleChatSessionKey("role-b", "role:role-a"), "role:role-b");
  });

  it("returns the empty-state title when no role is active", () => {
    assert.equal(resolveChatHeaderTitle({
      activeRoleName: null,
      activeSessionKey: "",
      sendingSessions: {},
    }), "选择一个角色");
  });

  it("keeps the active role name when another session is sending", () => {
    assert.equal(resolveChatHeaderTitle({
      activeRoleName: "Role B",
      activeSessionKey: "role:role-b",
      sendingSessions: {
        "role:role-a": "role-a",
      },
    }), "Role B");
  });

  it("shows the typing title only for the active sending session", () => {
    assert.equal(resolveChatHeaderTitle({
      activeRoleName: "Role A",
      activeSessionKey: "role:role-a",
      sendingSessions: {
        "role:role-a": "role-a",
      },
    }), "正在输入中...");
  });
});
