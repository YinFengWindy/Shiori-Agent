/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { findChatRetryTarget, findRetryableChatErrorKey, splitChatErrorContent } from "./chatFailedTurn";
import type { SessionMessage } from "../shared/types";

const user: SessionMessage = { id: "role:mira:4", role: "user", content: "帮我看看这张图", render_id: "local:user:1" };
const partial: SessionMessage = { role: "assistant", content: "我看", render_id: "local:assistant:2" };
const error: SessionMessage = { role: "error", content: "处理消息时出错，请稍后再试。", render_id: "local:error:3" };

describe("findRetryableChatErrorKey", () => {
  it("returns the latest error row when a persisted user message precedes it, even across a partial reply", () => {
    assert.equal(findRetryableChatErrorKey([user, partial, error]), "local:error:3");
  });

  it("is empty once the conversation has moved past the error", () => {
    assert.equal(findRetryableChatErrorKey([user, error, { id: "m9", role: "user", content: "算了", render_id: "u2" }]), "");
  });

  it("is empty when no user message was sent before the error", () => {
    assert.equal(findRetryableChatErrorKey([{ role: "assistant", content: "hi", render_id: "a" }, error]), "");
  });

  it("is empty when the user message never reached the bridge (no id to re-run)", () => {
    assert.equal(findRetryableChatErrorKey([{ ...user, id: undefined }, error]), "");
  });
});

describe("findChatRetryTarget", () => {
  it("names the persisted user message to re-run", () => {
    assert.deepEqual(findChatRetryTarget([user, partial, error], "local:error:3"), {
      errorKey: "local:error:3",
      userMessageId: "role:mira:4",
    });
  });

  it("refuses a stale error key", () => {
    assert.equal(findChatRetryTarget([user, partial, error], "local:error:9"), null);
  });
});

describe("splitChatErrorContent", () => {
  it("shows short messages inline", () => {
    assert.deepEqual(splitChatErrorContent("处理消息时出错，请稍后再试。"), { summary: "处理消息时出错，请稍后再试。", detail: "" });
  });

  it("keeps the message and puts the bridge-reported cause behind the detail toggle", () => {
    assert.deepEqual(
      splitChatErrorContent("处理消息时出错，请稍后再试。", "APIStatusError: 502 Bad Gateway"),
      { summary: "处理消息时出错，请稍后再试。", detail: "APIStatusError: 502 Bad Gateway" },
    );
  });

  it("moves long or multi-line errors behind a detail toggle", () => {
    const raw = "Connection error: upstream returned 502\nretry-after: 10";
    assert.deepEqual(splitChatErrorContent(raw), { summary: "回复失败", detail: raw });
  });
});
