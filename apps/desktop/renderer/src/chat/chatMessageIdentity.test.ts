/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  ensureChatMessageRenderId,
  getChatMessageDomKey,
  getChatMessageReactKey,
  reconcileSessionMessageRenderIds,
} from "./chatMessageIdentity";
import type { SessionMessage, SessionPayload } from "@shiori/sdk";

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

  it("keeps malformed media payloads from crashing render-id assignment", () => {
    const message = ensureChatMessageRenderId({
      role: "assistant",
      content: "hello",
      media: ["D:\\images\\mira.png", 7 as unknown as string],
    });

    assert.match(message.render_id ?? "", /^local:assistant:\d+$/);
  });
});

describe("reconcileSessionMessageRenderIds", () => {
  it("reserves a tool call identity before an unrelated text prefix can claim the stream", () => {
    const tool_chain = [{ text: "", reasoning_content: "", calls: [{ call_id: "call", name: "lookup", status: "success", arguments: {}, final_arguments: {}, result: "done" }] }];
    const stream = { role: "assistant", content: "partial", render_id: "local:tool", tool_chain };
    const reconciled = reconcileSessionMessageRenderIds(createSession([stream]), createSession([
      { id: "unrelated", role: "assistant", content: "partial unrelated" },
      { id: "actual", role: "assistant", content: "final", tool_chain },
    ]))!;
    assert.equal(reconciled.messages[0]!.render_id, "server:unrelated");
    assert.equal(reconciled.messages[1]!.render_id, stream.render_id);
  });

  it("reserves a live overlay key before matching an earlier persisted row", () => {
    const overlay = { role: "user", content: "hello", render_id: "local:user:overlay" };
    const incoming = createSession([{ id: "older", role: "user", content: "hello there" }, overlay]);
    const reconciled = reconcileSessionMessageRenderIds(createSession([overlay]), incoming)!;
    assert.equal(reconciled.messages[1]!.render_id, overlay.render_id);
    assert.notEqual(reconciled.messages[0]!.render_id, overlay.render_id);
  });

  it("allocates unique keys even when incoming keys collide with existing and generated identities", () => {
    const incoming = createSession([
      { role: "error", content: "one", render_id: "shared" },
      { id: "duplicate", role: "user", content: "two", render_id: "shared" },
      { role: "assistant", content: "three", render_id: "server:duplicate" },
    ]);
    const reconciled = reconcileSessionMessageRenderIds(null, incoming)!;
    assert.equal(new Set(reconciled.messages.map((message) => message.render_id)).size, 3);
    assert.equal(reconciled.messages[2]!.render_id, "server:duplicate");
    assert.equal(reconcileSessionMessageRenderIds(reconciled, reconciled), reconciled);
  });

  it("keeps distinct assistant rows sharing one request client id and repeated content", () => {
    const current = createSession([{ id: "a1", role: "assistant", content: "same", render_id: "local:assistant:original", metadata: { client_message_id: "turn" } }]);
    const incoming = createSession([
      { id: "a2", role: "assistant", content: "same", metadata: { client_message_id: "turn" } },
      { id: "a1", role: "assistant", content: "edited", metadata: { client_message_id: "turn" } },
    ]);
    const reconciled = reconcileSessionMessageRenderIds(current, incoming)!;
    assert.equal(reconciled.messages[0]!.render_id, "server:a2");
    assert.equal(reconciled.messages[1]!.render_id, "local:assistant:original");
  });

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

  it("reuses the optimistic render id by client message id", () => {
    const optimisticUserMessage = ensureChatMessageRenderId({
      role: "user",
      content: "发送中的内容",
      metadata: { client_message_id: "desktop-message-1" },
    });
    const currentSession = createSession([optimisticUserMessage]);
    const incomingSession = createSession([
      {
        id: "role:mira:1",
        role: "user",
        content: "服务端持久化内容",
        metadata: { client_message_id: "desktop-message-1", source: "desktop" },
      },
    ]);

    const reconciled = reconcileSessionMessageRenderIds(currentSession, incomingSession);

    assert.equal(reconciled?.messages[0]?.render_id, optimisticUserMessage.render_id);
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

  it("reuses the streaming assistant render id when Thinking arrives before content", () => {
    const streamingAssistantMessage = ensureChatMessageRenderId({
      role: "assistant",
      content: "",
      reasoning_content: "先分析",
      streaming: true,
    });
    const current = createSession([streamingAssistantMessage]);
    const incoming = createSession([{
      id: "assistant-1",
      role: "assistant",
      content: "正式回复",
      reasoning_content: "先分析问题",
    }]);

    const reconciled = reconcileSessionMessageRenderIds(current, incoming);

    assert.equal(reconciled?.messages[0]?.render_id, streamingAssistantMessage.render_id);
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
