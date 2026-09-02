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
    isSearchResultSessionActive: () => false,
    queueMessageNavigation: () => actions.push("queue-message"),
    clearMessageNavigation: () => actions.push("clear-message"),
    openRole: async () => {
      actions.push("open-role");
      return true;
    },
    loadMessagesAround: async () => {
      actions.push("load-around");
      return true;
    },
  };
}

describe("roleSearchNavigation", () => {
  it("enters the message view before opening a role result", async () => {
    const harness = createHarness();

    await navigateToRoleSearchResult({
      result: createResult("role"),
      messageKey: "",
      ...harness,
    });

    assert.deepEqual(harness.actions, ["open-chat", "clear-message", "open-role"]);
  });

  it("queues the message target before opening its role session", async () => {
    const harness = createHarness();

    await navigateToRoleSearchResult({
      result: createResult("message"),
      messageKey: "message-1",
      ...harness,
    });

    assert.deepEqual(harness.actions, ["open-chat", "clear-message", "queue-message", "open-role", "load-around"]);
  });

  it("keeps the current session mounted when its own historical message is selected", async () => {
    const harness = createHarness();
    harness.isSearchResultSessionActive = () => true;

    await navigateToRoleSearchResult({
      result: createResult("message"),
      messageKey: "message-1",
      ...harness,
    });

    assert.deepEqual(harness.actions, ["open-chat", "clear-message", "queue-message", "load-around"]);
  });

  it("clears a queued message target when opening its role session fails", async () => {
    const harness = createHarness();
    harness.openRole = async () => {
      harness.actions.push("open-role");
      return false;
    };

    await navigateToRoleSearchResult({
      result: createResult("message"),
      messageKey: "message-1",
      ...harness,
    });

    assert.deepEqual(harness.actions, ["open-chat", "clear-message", "queue-message", "open-role", "clear-message"]);
  });

  it("does not queue a DOM highlight when the persisted context cannot be loaded", async () => {
    const harness = createHarness();
    harness.loadMessagesAround = async () => {
      harness.actions.push("load-around");
      return false;
    };

    await navigateToRoleSearchResult({
      result: createResult("message"),
      messageKey: "message-1",
      ...harness,
    });

    assert.deepEqual(harness.actions, ["open-chat", "clear-message", "queue-message", "open-role", "load-around", "clear-message"]);
  });
});
