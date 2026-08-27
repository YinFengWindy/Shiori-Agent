/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  getChatAttachmentName,
  getChatMessageCopyText,
  getChatMessageReplyContent,
  getChatMessageSourceLabel,
  getStoredChatReplyPreview,
} from "./chatMessageActions";

describe("chatMessageActions", () => {
  it("normalizes attachment names and copyable text", () => {
    assert.equal(getChatAttachmentName("D:\\assets\\report.pdf"), "report.pdf");
    assert.equal(getChatAttachmentName("/tmp/photo.png"), "photo.png");
    assert.equal(getChatMessageCopyText({ role: "assistant", content: "  hello  " }), "hello");
  });

  it("uses media placeholders when quoted messages have no text", () => {
    assert.equal(getChatMessageReplyContent({ role: "assistant", content: "", media: ["photo.png"] }), "[图片]");
    assert.equal(getChatMessageReplyContent({ role: "assistant", content: "", media: ["report.pdf"] }), "[附件]");
    assert.equal(getChatMessageReplyContent({ role: "assistant", content: "", media: [] }), "");
  });

  it("resolves transport labels by metadata priority", () => {
    assert.equal(getChatMessageSourceLabel({
      role: "assistant",
      content: "hello",
      metadata: { transport_channel: "telegram", source: "desktop" },
    }), "TELEGRAM");
    assert.equal(getChatMessageSourceLabel({
      role: "assistant",
      content: "hello",
      metadata: { source: "desktop" },
    }), "DESKTOP");
    assert.equal(getChatMessageSourceLabel({ role: "assistant", content: "hello" }), null);
  });

  it("normalizes persisted reply metadata into a composer preview", () => {
    assert.deepEqual(getStoredChatReplyPreview({
      role: "assistant",
      content: "reply",
      metadata: {
        reply_to_message_id: "  source-1 ",
        reply_to_content: "  quoted content ",
        reply_to_sender: " Mira ",
      },
    }), {
      messageId: "source-1",
      content: "quoted content",
      sender: "Mira",
      preview: "quoted content",
    });
    assert.equal(getStoredChatReplyPreview({ role: "assistant", content: "reply" }), null);
  });
});
