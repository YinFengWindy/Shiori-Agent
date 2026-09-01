/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  getVirtualChatMessageWindow,
  chatMessageVirtualRowGap,
} from "./chatMessageVirtualization";
import type { SessionMessage } from "../shared/types";

function messages(count: number): SessionMessage[] {
  return Array.from({ length: count }, (_value, index) => ({
    id: `message-${index}`,
    role: index % 2 === 0 ? "assistant" : "user",
    content: `message ${index}`,
  }));
}

describe("getVirtualChatMessageWindow", () => {
  it("keeps a 10k-message React window bounded around the viewport", () => {
    const source = messages(10_000);
    const window = getVirtualChatMessageWindow({
      messages: source,
      messageKeys: source.map((message) => message.id ?? ""),
      measuredHeights: new Map(),
      scrollTop: 480_000,
      viewportHeight: 720,
      pinnedMessageIndex: -1,
    });

    assert.ok(window.messages.length < 80);
    assert.ok(window.startIndex > 0);
    assert.ok(window.endIndex < source.length);
    assert.ok(window.topSpacerHeight > 0);
    assert.ok(window.bottomSpacerHeight > 0);
  });

  it("uses measured rows for spacer totals and mounts an offscreen pinned search result", () => {
    const source = messages(100);
    const window = getVirtualChatMessageWindow({
      messages: source,
      messageKeys: source.map((message) => message.id ?? ""),
      measuredHeights: new Map([["message-0", 300]]),
      scrollTop: 8_000,
      viewportHeight: 600,
      pinnedMessageIndex: 4,
    });

    assert.equal(window.startIndex, 0);
    assert.ok(window.endIndex >= 5);
    assert.equal(window.topSpacerHeight, 0);
    assert.ok(window.totalHeight >= 300 + chatMessageVirtualRowGap);
  });

  it("keeps the last row mounted when the scroll position reaches total height", () => {
    const source = messages(12);
    const window = getVirtualChatMessageWindow({
      messages: source,
      messageKeys: source.map((message) => message.id ?? ""),
      measuredHeights: new Map(),
      scrollTop: Number.POSITIVE_INFINITY,
      viewportHeight: 720,
      pinnedMessageIndex: -1,
    });

    assert.equal(window.messages.at(-1)?.id, "message-11");
    assert.equal(window.endIndex, source.length);
  });
});
