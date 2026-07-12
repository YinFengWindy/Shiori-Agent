/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { mergeIncomingSessionDuringSend } from "./chatSessionMerge.js";
import type { SessionMessage, SessionPayload } from "../shared/types.js";

function createSession(messages: SessionMessage[]): SessionPayload {
  return {
    key: "role:mira",
    created_at: "2026-07-05T11:00:00+08:00",
    updated_at: "2026-07-05T11:00:00+08:00",
    last_consolidated: 0,
    metadata: { role_id: "mira" },
    messages,
  };
}

describe("mergeIncomingSessionDuringSend", () => {
  it("keeps the optimistic user turn when a stale shorter snapshot arrives during sending", () => {
    const currentSession = createSession([
      {
        id: "role:mira:1",
        role: "assistant",
        content: "上一条消息",
      },
      {
        role: "user",
        content: "刚发出去的消息",
      },
    ]);
    const incomingSession = createSession([
      {
        id: "role:mira:1",
        role: "assistant",
        content: "上一条消息",
      },
    ]);

    const merged = mergeIncomingSessionDuringSend(currentSession, incomingSession, true);

    assert.deepEqual(merged?.messages, currentSession.messages);
  });

  it("keeps the optimistic user turn even after sending flips false when a stale snapshot arrives late", () => {
    const currentSession = createSession([
      {
        id: "role:mira:1",
        role: "assistant",
        content: "上一条消息",
      },
      {
        role: "user",
        content: "刚发出去的消息",
      },
    ]);
    const incomingSession = createSession([
      {
        id: "role:mira:1",
        role: "assistant",
        content: "上一条消息",
      },
    ]);

    const merged = mergeIncomingSessionDuringSend(currentSession, incomingSession, false);

    assert.deepEqual(merged?.messages, currentSession.messages);
  });

  it("inserts the optimistic user turn back into a same-length stale snapshot", () => {
    const currentSession = createSession([
      {
        id: "role:mira:1",
        role: "assistant",
        content: "上一条消息",
      },
      {
        role: "user",
        content: "刚发出去的消息",
      },
    ]);
    const incomingSession = createSession([
      {
        id: "role:mira:1",
        role: "assistant",
        content: "上一条消息",
      },
      {
        role: "assistant",
        content: "角色处理中",
      },
    ]);

    const merged = mergeIncomingSessionDuringSend(currentSession, incomingSession, true);

    assert.deepEqual(merged?.messages, [
      incomingSession.messages[0],
      currentSession.messages[1],
      incomingSession.messages[1],
    ]);
  });

  it("accepts the incoming session once it already contains the persisted user turn", () => {
    const currentSession = createSession([
      {
        id: "role:mira:1",
        role: "assistant",
        content: "上一条消息",
      },
      {
        role: "user",
        content: "刚发出去的消息",
      },
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
      {
        id: "role:mira:3",
        role: "assistant",
        content: "收到",
      },
    ]);

    const merged = mergeIncomingSessionDuringSend(currentSession, incomingSession, true);

    assert.equal(merged, incomingSession);
  });

  it("accepts divergent incoming snapshots instead of forcing the optimistic turn into unrelated history", () => {
    const currentSession = createSession([
      {
        id: "role:mira:1",
        role: "assistant",
        content: "上一条消息",
      },
      {
        role: "user",
        content: "刚发出去的消息",
      },
    ]);
    const incomingSession = createSession([
      {
        id: "role:mira:1",
        role: "assistant",
        content: "上一条消息（已变更）",
      },
    ]);

    const merged = mergeIncomingSessionDuringSend(currentSession, incomingSession, true);

    assert.equal(merged, incomingSession);
  });

  it("keeps an identified optimistic turn when a stale snapshot has divergent history", () => {
    const optimisticUserMessage: SessionMessage = {
      role: "user",
      content: "刚发出去的消息",
      metadata: { client_message_id: "desktop-message-1" },
    };
    const currentSession = createSession([
      {
        id: "role:mira:1",
        role: "assistant",
        content: "上一条消息",
      },
      optimisticUserMessage,
    ]);
    const incomingSession = createSession([
      {
        id: "role:mira:1",
        role: "assistant",
        content: "上一条消息（服务端旧快照）",
      },
    ]);

    const merged = mergeIncomingSessionDuringSend(currentSession, incomingSession, true);

    assert.deepEqual(merged?.messages, [incomingSession.messages[0], optimisticUserMessage]);
  });

  it("preserves fresh incoming metadata while keeping the optimistic local user turn", () => {
    const currentSession = createSession([
      {
        id: "role:mira:1",
        role: "assistant",
        content: "上一条消息",
      },
      {
        role: "user",
        content: "刚发出去的消息",
      },
    ]);
    currentSession.metadata = {
      role_id: "mira",
      current_mood: "平静",
    };
    const incomingSession = createSession([
      {
        id: "role:mira:1",
        role: "assistant",
        content: "上一条消息",
      },
    ]);
    incomingSession.metadata = {
      role_id: "mira",
      current_mood: "开心",
    };

    const merged = mergeIncomingSessionDuringSend(currentSession, incomingSession, true);

    assert.deepEqual(merged?.messages, currentSession.messages);
    assert.equal(merged?.metadata.current_mood, "开心");
  });

  it("keeps the current local tail when chat.send resolves with an older shorter snapshot after streaming already started", () => {
    const currentSession = createSession([
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
      {
        role: "assistant",
        content: "她",
      },
    ]);
    currentSession.metadata = {
      role_id: "mira",
      current_mood: "平静",
    };
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
    incomingSession.metadata = {
      role_id: "mira",
      current_mood: "开心",
    };

    const merged = mergeIncomingSessionDuringSend(currentSession, incomingSession, true);

    assert.deepEqual(merged?.messages, [
      incomingSession.messages[0],
      incomingSession.messages[1],
      currentSession.messages[2],
    ]);
    assert.equal(merged?.metadata.current_mood, "开心");
  });

  it("keeps the current local tail even after sending flips false when a shorter equivalent snapshot arrives late", () => {
    const currentSession = createSession([
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
      {
        role: "assistant",
        content: "她停",
      },
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

    const merged = mergeIncomingSessionDuringSend(currentSession, incomingSession, false);

    assert.deepEqual(merged?.messages, [
      incomingSession.messages[0],
      incomingSession.messages[1],
      currentSession.messages[2],
    ]);
  });

  it("treats malformed media payloads as empty instead of throwing during merge", () => {
    const currentSession = createSession([
      {
        id: "role:mira:1",
        role: "assistant",
        content: "上一条消息",
        media: ["D:\\images\\mira.png", 9 as unknown as string],
      },
      {
        role: "user",
        content: "刚发出去的消息",
      },
    ]);
    const incomingSession = createSession([
      {
        id: "role:mira:1",
        role: "assistant",
        content: "上一条消息",
        media: ["D:\\images\\mira.png"],
      },
    ]);

    const merged = mergeIncomingSessionDuringSend(currentSession, incomingSession, true);

    assert.deepEqual(merged?.messages, [
      {
        id: "role:mira:1",
        role: "assistant",
        content: "上一条消息",
        media: ["D:\\images\\mira.png"],
      },
      {
        role: "user",
        content: "刚发出去的消息",
      },
    ]);
  });
});
