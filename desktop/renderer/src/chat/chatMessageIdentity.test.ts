/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  ensureChatMessageRenderId,
  getChatMessageDomKey,
  getChatMessageReactKey,
  reconcileSessionMessageRenderIds,
} from "./chatMessageIdentity";
import type { SessionMessage, SessionPayload } from "../shared/types";

function createSession(messages: SessionMessage[]): SessionPayload {
  return {
    key: "role:mira",
    created_at: "2026-07-07T12:00:00+08:00",
    updated_at: "2026-07-07T12:00:00+08:00",
    last_consolidated: 0,
    metadata: { role_id: "mira" },
    messages,
  };
}

describe("ensureChatMessageRenderId", () => {
  it("assigns a local render id to optimistic messages without a persisted id", () => {
    const message = ensureChatMessageRenderId({
      role: "user",
      content: "hello",
    });

    assert.match(message.render_id ?? "", /^local:user:\d+$/);
  });
});

describe("reconcileSessionMessageRenderIds", () => {
  it("reuses the optimistic user render id after the authoritative snapshot adds a persisted id", () => {
    const optimisticUserMessage = ensureChatMessageRenderId({
      role: "user",
      content: "刚发出去的消息",
    });
    const currentSession = createSession([
      {
        id: "role:mira:1",
        role: "assistant",
        content: "上一条消息",
        render_id: "server:role:mira:1",
      },
      optimisticUserMessage,
    ]);
    const incomingSession = createSession([
      {
        id: "role:mira:1",
        role: "assistant",
        content: "上一条消息",
      },
      {
        id: "role:mira:2",
        role: "user",
        content: "刚发出去的消息",
      },
    ]);

    const reconciled = reconcileSessionMessageRenderIds(currentSession, incomingSession);

    assert.equal(reconciled?.messages[1]?.render_id, optimisticUserMessage.render_id);
    assert.equal(getChatMessageReactKey(reconciled?.messages[1] as SessionMessage, 1), optimisticUserMessage.render_id);
  });

  it("reuses the streaming assistant render id when the authoritative snapshot extends the same reply", () => {
    const streamingAssistantMessage = ensureChatMessageRenderId({
      role: "assistant",
      content: "她停顿",
    });
    const currentSession = createSession([
      {
        id: "role:mira:1",
        role: "user",
        content: "在吗",
        render_id: "server:role:mira:1",
      },
      streamingAssistantMessage,
    ]);
    const incomingSession = createSession([
      {
        id: "role:mira:1",
        role: "user",
        content: "在吗",
      },
      {
        id: "role:mira:2",
        role: "assistant",
        content: "她停顿了一下，然后把声音放轻。",
      },
    ]);

    const reconciled = reconcileSessionMessageRenderIds(currentSession, incomingSession);

    assert.equal(reconciled?.messages[1]?.render_id, streamingAssistantMessage.render_id);
  });
});

describe("getChatMessageDomKey", () => {
  it("keeps DOM lookup keys pinned to the persisted message id", () => {
    assert.equal(
      getChatMessageDomKey(
        {
          id: "message-1",
          render_id: "local:user:1",
          role: "user",
          content: "hello",
        },
        0,
      ),
      "message-1",
    );
  });
});
