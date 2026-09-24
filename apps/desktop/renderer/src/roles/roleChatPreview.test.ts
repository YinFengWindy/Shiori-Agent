/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  extractChatPreviewText,
  formatChatListTime,
  previewFromRoleLastMessage,
  previewFromSessionMessages,
} from "./roleChatPreview";

describe("extractChatPreviewText", () => {
  it("strips emphasis, headings, links and list markers into one line", () => {
    assert.equal(
      extractChatPreviewText("## 今天\n\n- **记得**带伞\n- 看 [天气](https://example.com)\n> 引用一句"),
      "今天 记得带伞 看 天气 引用一句",
    );
  });

  it("replaces fenced code with a placeholder and keeps inline code text", () => {
    assert.equal(extractChatPreviewText("试试 `npm i`：\n```bash\nnpm run dev\n```\n好了"), "试试 npm i： [代码] 好了");
  });

  it("flattens tables and images", () => {
    assert.equal(extractChatPreviewText("![猫](a.png)\n| A | B |\n| --- | --- |\n| 1 | 2 |"), "猫 A B 1 2");
  });

  it("keeps snake_case and arithmetic intact", () => {
    assert.equal(extractChatPreviewText("set max_steps to 2*3"), "set max_steps to 2*3");
  });
});

describe("chat list previews", () => {
  it("prefixes the user's own last message", () => {
    assert.deepEqual(
      previewFromRoleLastMessage({ role: "user", content: "晚安", timestamp: "t", has_media: false }),
      { text: "你：晚安", timestamp: "t" },
    );
  });

  it("uses an image placeholder for media-only messages", () => {
    assert.equal(previewFromRoleLastMessage({ role: "assistant", content: "", timestamp: "t", has_media: true })?.text, "[图片]");
  });

  it("follows the open conversation, skipping error rows", () => {
    assert.deepEqual(previewFromSessionMessages([
      { role: "assistant", content: "**好的**", timestamp: "t1" },
      { role: "error", content: "处理消息时出错" },
    ]), { text: "好的", timestamp: "t1" });
  });

  it("is null for an empty conversation", () => {
    assert.equal(previewFromSessionMessages([]), null);
    assert.equal(previewFromRoleLastMessage(null), null);
  });
});

describe("formatChatListTime", () => {
  const now = new Date(2026, 8, 24, 16, 30);

  it("shows a clock time today", () => {
    assert.equal(formatChatListTime(new Date(2026, 8, 24, 9, 5).toISOString(), now), "09:05");
  });

  it("shows 昨天 and weekdays within the week", () => {
    assert.equal(formatChatListTime(new Date(2026, 8, 23, 23, 0).toISOString(), now), "昨天");
    assert.equal(formatChatListTime(new Date(2026, 8, 20, 12, 0).toISOString(), now), "周日");
  });

  it("shows month/day this year and the year before that", () => {
    assert.equal(formatChatListTime(new Date(2026, 5, 1, 12, 0).toISOString(), now), "6/1");
    assert.equal(formatChatListTime(new Date(2025, 11, 31, 12, 0).toISOString(), now), "2025/12/31");
  });

  it("is empty for missing or unreadable timestamps", () => {
    assert.equal(formatChatListTime("", now), "");
    assert.equal(formatChatListTime("not a date", now), "");
  });
});
