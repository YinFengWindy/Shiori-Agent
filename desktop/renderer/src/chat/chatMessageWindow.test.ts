/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  getExpandedVisibleChatMessageCountForKey,
  getVisibleChatMessages,
  getVisibleChatMessageStartIndex,
} from "./chatMessageWindow";
import type { SessionMessage } from "../shared/types";

function createMessages(count: number): SessionMessage[] {
  return Array.from({ length: count }, (_value, index) => ({
    id: `message-${index + 1}`,
    role: index % 2 === 0 ? "assistant" : "user",
    content: `message-${index + 1}`,
  }));
}

describe("getVisibleChatMessageStartIndex", () => {
  it("pins the default render window to the newest chat messages", () => {
    assert.equal(getVisibleChatMessageStartIndex(240, 60), 180);
  });
});

describe("getVisibleChatMessages", () => {
  it("returns only the visible tail and reports how many messages stay hidden", () => {
    const result = getVisibleChatMessages(createMessages(5), 2);

    assert.equal(result.startIndex, 3);
    assert.equal(result.hiddenMessageCount, 3);
    assert.deepEqual(result.messages.map((message) => message.id), ["message-4", "message-5"]);
  });
});

describe("getExpandedVisibleChatMessageCountForKey", () => {
  it("expands the render window when a highlighted message lives above the current slice", () => {
    const messages = createMessages(300);

    const nextVisibleCount = getExpandedVisibleChatMessageCountForKey(messages, 60, "message-40");

    assert.equal(nextVisibleCount, 285);
  });

  it("keeps the current render window when the highlighted message is already visible", () => {
    const messages = createMessages(300);

    const nextVisibleCount = getExpandedVisibleChatMessageCountForKey(messages, 60, "message-280");

    assert.equal(nextVisibleCount, 60);
  });
});
