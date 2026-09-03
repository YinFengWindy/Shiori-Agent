/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  getPaginatedChatMessageWindow,
  getPrependAnchorScrollTop,
  shouldLoadOlderChatMessages,
  shouldLoadOlderChatMessagesAfterSessionRestore,
  triggerOlderChatMessagesLoad,
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
  it("keeps every server-loaded message available to the data window and reports remote history as hidden", () => {
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

  it("does not count optimistic messages as loaded persisted history", () => {
    const current = session(2);
    current.messages[0]!.seq = 198;
    current.messages[1]!.seq = 199;
    current.messages.push({ role: "user", content: "optimistic" });
    current.pagination = {
      limit: 50,
      has_more: true,
      oldest_seq: 198,
      newest_seq: 199,
      total_count: 200,
      before_seq: null,
      next_before_seq: 198,
    };

    assert.equal(getPaginatedChatMessageWindow(current, 10).hiddenMessageCount, 198);
  });
});

describe("getPrependAnchorScrollTop", () => {
  it("compensates exactly for the height added above the visible anchor", () => {
    assert.equal(getPrependAnchorScrollTop(800, 280, 1260), 740);
  });
});

describe("shouldLoadOlderChatMessages", () => {
  it("triggers only for a user scroll within the top threshold", () => {
    const base = { canLoadOlderMessages: true, loading: false, isAutoScrolling: false };

    assert.equal(shouldLoadOlderChatMessages({ ...base, scrollTop: 96 }), true);
    assert.equal(shouldLoadOlderChatMessages({ ...base, scrollTop: 0 }), true);
    assert.equal(shouldLoadOlderChatMessages({ ...base, scrollTop: 97 }), false);
    assert.equal(shouldLoadOlderChatMessages({ ...base, scrollTop: 96, loading: true }), false);
    assert.equal(shouldLoadOlderChatMessages({ ...base, scrollTop: 96, canLoadOlderMessages: false }), false);
    assert.equal(shouldLoadOlderChatMessages({ ...base, scrollTop: 96, isAutoScrolling: true }), false);
  });
});

describe("triggerOlderChatMessagesLoad", () => {
  const base = {
    canLoadOlderMessages: true,
    loading: false,
    isAutoScrolling: false,
  };

  it("routes a near-top user scroll to the older-page loader", () => {
    let loadCount = 0;
    const triggered = triggerOlderChatMessagesLoad({
      ...base,
      scrollTop: 0,
      loadOlderPage: () => { loadCount += 1; },
    });

    assert.equal(triggered, true);
    assert.equal(loadCount, 1);
  });

  it("keeps the loading gate from invoking a duplicate request", () => {
    let loadCount = 0;
    const loadOlderPage = () => { loadCount += 1; };
    const first = triggerOlderChatMessagesLoad({ ...base, scrollTop: 24, loadOlderPage });
    const duplicate = triggerOlderChatMessagesLoad({ ...base, scrollTop: 24, loading: true, loadOlderPage });

    assert.equal(first, true);
    assert.equal(duplicate, false);
    assert.equal(loadCount, 1);
  });

  it("does not route programmatic scrolling or positions outside the threshold", () => {
    let loadCount = 0;
    const loadOlderPage = () => { loadCount += 1; };
    assert.equal(triggerOlderChatMessagesLoad({ ...base, scrollTop: 0, isAutoScrolling: true, loadOlderPage }), false);
    assert.equal(triggerOlderChatMessagesLoad({ ...base, scrollTop: 97, loadOlderPage }), false);
    assert.equal(loadCount, 0);
  });
});

describe("shouldLoadOlderChatMessagesAfterSessionRestore", () => {
  const base = {
    canLoadOlderMessages: true,
    loading: false,
  };

  it("checks for older history when a non-bottom session restores near the top", () => {
    assert.equal(shouldLoadOlderChatMessagesAfterSessionRestore({
      ...base,
      scrollTop: 0,
      restoredWasAtBottom: false,
    }), true);
  });

  it("does not treat the initial bottom restore as a pagination request", () => {
    assert.equal(shouldLoadOlderChatMessagesAfterSessionRestore({
      ...base,
      scrollTop: 0,
      restoredWasAtBottom: true,
    }), false);
  });

  it("keeps the same loading and threshold gates as user scrolling", () => {
    assert.equal(shouldLoadOlderChatMessagesAfterSessionRestore({
      ...base,
      scrollTop: 97,
      restoredWasAtBottom: false,
    }), false);
    assert.equal(shouldLoadOlderChatMessagesAfterSessionRestore({
      ...base,
      loading: true,
      scrollTop: 0,
      restoredWasAtBottom: false,
    }), false);
    assert.equal(shouldLoadOlderChatMessagesAfterSessionRestore({
      ...base,
      canLoadOlderMessages: false,
      scrollTop: 0,
      restoredWasAtBottom: false,
    }), false);
  });
});
