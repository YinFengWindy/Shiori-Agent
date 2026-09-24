/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolveChatHeaderTitle, resolveVisibleChatSessionKey } from "./chatHeaderState";

describe("resolveChatHeaderTitle", () => {
  it("prefers the active role session key over the stale active session key during role switches", () => {
    assert.equal(resolveVisibleChatSessionKey("role-b", "role:role-a"), "role:role-b");
  });

  it("returns the empty-state title when no role is active", () => {
    assert.equal(resolveChatHeaderTitle(null), "选择一个角色");
  });

  it("keeps the role name as the title; typing is shown separately", () => {
    assert.equal(resolveChatHeaderTitle("Role A"), "Role A");
  });
});
