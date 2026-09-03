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
  it("keeps the mounted message window bounded at 1k, 5k, and 10k history sizes", () => {
    for (const count of [1_000, 5_000, 10_000]) {
      const source = messages(count);
      const messageKeys = source.map((message) => message.id ?? "");
      const totalHeight = getVirtualChatMessageWindow({
        messages: source,
        messageKeys,
        measuredHeights: new Map(),
        scrollTop: Number.POSITIVE_INFINITY,
        viewportHeight: 720,
        pinnedMessageIndex: -1,
      }).totalHeight;

      for (const [position, scrollTop] of [
        ["top", 0],
        ["middle", totalHeight / 2],
        ["bottom", Number.POSITIVE_INFINITY],
      ] as const) {
        const window = getVirtualChatMessageWindow({
          messages: source,
          messageKeys,
          measuredHeights: new Map(),
          scrollTop,
          viewportHeight: 720,
          pinnedMessageIndex: -1,
        });

        assert.ok(
          window.messages.length < 80,
          `${count} messages at the ${position} must mount fewer than 80 rows`,
        );
        assert.equal(window.messages[0]?.id, `message-${window.startIndex}`);
        assert.equal(window.messages.at(-1)?.id, `message-${window.endIndex - 1}`);
        if (position === "top") {
          assert.equal(window.topSpacerHeight, 0);
        } else if (position === "middle") {
          assert.ok(window.topSpacerHeight > 0);
          assert.ok(window.bottomSpacerHeight > 0);
        } else {
          assert.equal(window.bottomSpacerHeight, 0);
        }
      }
    }
  });

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
