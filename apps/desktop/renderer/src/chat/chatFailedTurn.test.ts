/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { buildChatRetryRequest, findRetryableChatErrorKey, splitChatErrorContent } from "./chatFailedTurn";
import type { SessionMessage } from "../shared/types";

const user: SessionMessage = {
  role: "user",
  content: "帮我看看这张图",
  media: ["D:/a.png"],
  render_id: "local:user:1",
  metadata: { reply_to_message_id: "m1", reply_to_content: "上一条", reply_to_sender: "Mira" },
};
const partial: SessionMessage = { role: "assistant", content: "我看", render_id: "local:assistant:2" };
const error: SessionMessage = { role: "error", content: "处理消息时出错，请稍后再试。", render_id: "local:error:3" };

describe("findRetryableChatErrorKey", () => {
  it("returns the latest error row when a user message precedes it, even across a partial reply", () => {
    assert.equal(findRetryableChatErrorKey([user, partial, error]), "local:error:3");
  });

  it("is empty once the conversation has moved past the error", () => {
    assert.equal(findRetryableChatErrorKey([user, error, { role: "user", content: "算了", render_id: "u2" }]), "");
  });

  it("is empty when no user message was sent before the error", () => {
    assert.equal(findRetryableChatErrorKey([{ role: "assistant", content: "hi", render_id: "a" }, error]), "");
  });
});

describe("buildChatRetryRequest", () => {
  it("re-sends the same text, attachments and quote", () => {
    assert.deepEqual(buildChatRetryRequest([user, partial, error], "local:error:3"), {
      content: "帮我看看这张图",
      attachments: ["D:/a.png"],
      replyTarget: { messageId: "m1", content: "上一条", sender: "Mira", preview: "上一条" },
    });
  });

  it("refuses a stale error key", () => {
    assert.equal(buildChatRetryRequest([user, partial, error], "local:error:9"), null);
  });
});

describe("splitChatErrorContent", () => {
  it("shows short messages inline", () => {
    assert.deepEqual(splitChatErrorContent("处理消息时出错，请稍后再试。"), { summary: "处理消息时出错，请稍后再试。", detail: "" });
  });

  it("moves long or multi-line errors behind a detail toggle", () => {
    const raw = "Connection error: upstream returned 502\nretry-after: 10";
    assert.deepEqual(splitChatErrorContent(raw), { summary: "回复失败", detail: raw });
  });
});
