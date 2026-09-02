/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  shouldAutoScrollOnContentSizeChange,
  shouldAutoScrollOnNewMessage,
} from "./chatAutoScroll";

describe("shouldAutoScrollOnNewMessage", () => {
  it("does not return to the bottom while historical message navigation is highlighted", () => {
    assert.equal(
      shouldAutoScrollOnNewMessage({
        currentMessageCount: 3,
        previousMessageCount: 1,
        lastMessageContent: "最新",
        previousLastMessageContent: "命中附近",
        highlightedMessageKey: "role:mira:2",
        sending: false,
        wasAtBottom: true,
      }),
      false,
    );
  });

  it("scrolls when a new message is appended and the viewer was already at the bottom", () => {
    assert.equal(
      shouldAutoScrollOnNewMessage({
        currentMessageCount: 3,
        previousMessageCount: 2,
        lastMessageContent: "收到",
        previousLastMessageContent: "你好",
        highlightedMessageKey: "",
        sending: false,
        wasAtBottom: true,
      }),
      true,
    );
  });

  it("keeps following streaming reply growth while the viewer stays at the bottom", () => {
    assert.equal(
      shouldAutoScrollOnNewMessage({
        currentMessageCount: 2,
        previousMessageCount: 2,
        lastMessageContent: "收到啦，我继续说完这句",
        previousLastMessageContent: "收到啦",
        highlightedMessageKey: "",
        sending: false,
        wasAtBottom: true,
      }),
      true,
    );
  });

  it("does not scroll when neither message count nor the last message content changed", () => {
    assert.equal(
      shouldAutoScrollOnNewMessage({
        currentMessageCount: 2,
        previousMessageCount: 2,
        lastMessageContent: "收到啦",
        previousLastMessageContent: "收到啦",
        highlightedMessageKey: "",
        sending: false,
        wasAtBottom: true,
      }),
      false,
    );
  });

  it("does not yank the viewport when the viewer already left the bottom", () => {
    assert.equal(
      shouldAutoScrollOnNewMessage({
        currentMessageCount: 2,
        previousMessageCount: 2,
        lastMessageContent: "收到啦，我继续说完这句",
        previousLastMessageContent: "收到啦",
        highlightedMessageKey: "",
        sending: false,
        wasAtBottom: false,
      }),
      false,
    );
  });
});

describe("shouldAutoScrollOnContentSizeChange", () => {
  it("keeps a bottom-following chat at the bottom after row measurement", () => {
    assert.equal(
      shouldAutoScrollOnContentSizeChange({ highlightedMessageKey: "", wasAtBottom: true }),
      true,
    );
  });

  it("does not reposition a viewer who scrolled upward", () => {
    assert.equal(
      shouldAutoScrollOnContentSizeChange({ highlightedMessageKey: "", wasAtBottom: false }),
      false,
    );
  });
});
