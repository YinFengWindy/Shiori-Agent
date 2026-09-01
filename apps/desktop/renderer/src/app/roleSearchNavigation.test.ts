/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { navigateToRoleSearchResult } from "./roleSearchNavigation";
import type { RoleSearchResult } from "../shared/types";

function createResult(matchedField: RoleSearchResult["matchedField"]): RoleSearchResult {
  return {
    roleId: "mira",
    roleName: "Mira",
    roleAvatarAbs: null,
    sessionKey: "role:mira",
    matchedMessageTimestamp: null,
    matchedMessageId: matchedField === "message" ? "message-1" : null,
    matchedMessageIndex: matchedField === "message" ? 0 : null,
    matchedMessagePreview: matchedField === "message" ? "hello" : "角色 Mira",
    matchedField,
  };
}

function createHarness() {
  const actions: string[] = [];
  return {
    actions,
    openChatView: () => actions.push("open-chat"),
    queueMessageNavigation: () => actions.push("queue-message"),
    clearMessageNavigation: () => actions.push("clear-message"),
    openRole: async () => {
      actions.push("open-role");
      return true;
    },
  };
}

describe("roleSearchNavigation", () => {
  it("enters the message view before opening a role result", () => {
    const harness = createHarness();

    navigateToRoleSearchResult({
      result: createResult("role"),
      messageKey: "",
      ...harness,
    });

    assert.deepEqual(harness.actions, ["open-chat", "clear-message", "open-role"]);
  });

  it("enters the message view before queuing a message result", () => {
    const harness = createHarness();

    navigateToRoleSearchResult({
      result: createResult("message"),
      messageKey: "message-1",
      ...harness,
    });

    assert.deepEqual(harness.actions, ["open-chat", "queue-message", "open-role"]);
  });
});
