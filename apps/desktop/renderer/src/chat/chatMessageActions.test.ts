/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  getChatAttachmentName,
  getChatMessageCopyText,
  getChatMessageReplyContent,
  getChatMessageSourceLabel,
  getChatMessageActionAvailability,
  getStoredChatReplyPreview,
  isInterruptedChatMessage,
} from "./chatMessageActions";

describe("chatMessageActions", () => {
  it("normalizes attachment names and copyable text", () => {
    assert.equal(getChatAttachmentName("D:\\assets\\report.pdf"), "report.pdf");
    assert.equal(getChatAttachmentName("/tmp/photo.png"), "photo.png");
    assert.equal(getChatMessageCopyText({ role: "assistant", content: "  hello  " }), "hello");
  });

  it("preserves assistant Markdown source for copy actions", () => {
    const markdown = "**bold**\n\n| A | B |\n| --- | --- |\n| 1 | 2 |";
    assert.equal(getChatMessageCopyText({ role: "assistant", content: `  ${markdown}  ` }), markdown);
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
    }), "telegram");
    assert.equal(getChatMessageSourceLabel({
      role: "assistant",
      content: "hello",
      metadata: { source: "desktop" },
    }), "桌面端");
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

describe("chat message source label", () => {
  it("labels a plugin channel from the channels.list catalog", () => {
    const catalog = [{ name: "qqbot", label: "QQ 机器人" }] as unknown as Parameters<typeof getChatMessageSourceLabel>[1];
    assert.equal(getChatMessageSourceLabel({
      role: "user",
      content: "hi",
      metadata: { transport_channel: "QQBot" },
    }, catalog), "QQ 机器人");
  });
});

describe("chat message action availability", () => {
  const idle = { sending: false, retryable: false };

  it("offers copy and quote on a finished reply", () => {
    assert.deepEqual(
      getChatMessageActionAvailability({ role: "assistant", content: "好的" }, idle),
      { copy: true, quote: true, retry: false },
    );
  });

  it("offers nothing while the reply is still streaming", () => {
    assert.deepEqual(
      getChatMessageActionAvailability({ role: "assistant", content: "正在", streaming: true }, idle),
      { copy: false, quote: false, retry: false },
    );
  });

  it("locks quoting while a reply is in flight but keeps copy", () => {
    assert.deepEqual(
      getChatMessageActionAvailability({ role: "user", content: "在吗" }, { sending: true, retryable: false }),
      { copy: true, quote: false, retry: false },
    );
  });

  it("offers retry only on the retryable error row and never quote", () => {
    const error = { role: "error", content: "处理消息时出错，请稍后再试。" };
    assert.deepEqual(getChatMessageActionAvailability(error, { sending: false, retryable: true }), { copy: true, quote: false, retry: true });
    assert.equal(getChatMessageActionAvailability(error, idle).retry, false);
    assert.equal(getChatMessageActionAvailability(error, { sending: true, retryable: true }).retry, false);
  });
});

describe("interrupted reply detection", () => {
  it("recognizes the persisted interrupted marker on a finished reply", () => {
    assert.equal(isInterruptedChatMessage({ role: "assistant", content: "说到一半", metadata: { interrupted_reply: true } }), true);
  });

  it("ignores finished, streaming and non-assistant rows", () => {
    assert.equal(isInterruptedChatMessage({ role: "assistant", content: "完整回复" }), false);
    assert.equal(isInterruptedChatMessage({ role: "assistant", content: "…", streaming: true, metadata: { interrupted_reply: true } }), false);
    assert.equal(isInterruptedChatMessage({ role: "user", content: "hi", metadata: { interrupted_reply: true } }), false);
  });
});
