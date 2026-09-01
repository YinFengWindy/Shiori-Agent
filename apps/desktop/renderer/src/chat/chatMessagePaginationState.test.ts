/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  getPaginatedChatMessageWindow,
  getPrependAnchorScrollTop,
} from "./chatMessagePaginationState";
import type { SessionPayload } from "../shared/types";

function session(messages: number): SessionPayload {
  return {
    key: "role:mira",
    created_at: "2026-09-01T00:00:00+08:00",
    updated_at: "2026-09-01T00:00:00+08:00",
    last_consolidated: 0,
    metadata: {},
    messages: Array.from({ length: messages }, (_value, index) => ({
      id: `role:mira:${index}`,
      seq: index,
      role: "assistant",
      content: String(index),
    })),
  };
}

describe("getPaginatedChatMessageWindow", () => {
  it("renders every server-loaded message and reports only remote history as hidden", () => {
    const current = session(50);
    current.pagination = {
      limit: 50,
      has_more: true,
      oldest_seq: 150,
      newest_seq: 199,
      total_count: 200,
      before_seq: null,
      next_before_seq: 150,
    };

    const window = getPaginatedChatMessageWindow(current, 10);

    assert.equal(window.startIndex, 0);
    assert.equal(window.messages.length, 50);
    assert.equal(window.hiddenMessageCount, 150);
  });
});

describe("getPrependAnchorScrollTop", () => {
  it("compensates exactly for the height added above the visible anchor", () => {
    assert.equal(getPrependAnchorScrollTop(800, 280, 1260), 740);
  });
});
