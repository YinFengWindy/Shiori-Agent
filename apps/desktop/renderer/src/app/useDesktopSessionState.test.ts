/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { mergeIncomingSessionDuringSend } from "../chat/chatSessionMerge";
import {
  canSendSessionState,
  clearAllSendingSessionsState,
  clearSendingSessionState,
  markSendingSessionState,
  parseOpenedSessionPayload,
  parseSessionMessageUpdatePayload,
} from "./useDesktopSessionState";
import {
  mergeSessionMessagePage,
  mergeSessionMessagesAround,
  mergeSessionSummaryAndMessage,
  parseSessionMessagesAround,
} from "./sessionMessagePagination";
import type { SessionMessage, SessionPayload } from "../shared/types";

function createSession(messages: SessionMessage[]): SessionPayload {
  return {
    key: "role:shiori",
    created_at: "2026-07-06T12:00:00+08:00",
    updated_at: "2026-07-06T12:00:00+08:00",
    last_consolidated: 0,
    metadata: { role_id: "shiori" },
    messages,
  };
}

describe("markSendingSessionState", () => {
  it("marks the session as sending before a stale session snapshot is merged", () => {
    const currentSession = createSession([
      {
        id: "role:shiori:1",
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
        id: "role:shiori:1",
        role: "assistant",
        content: "上一条消息",
      },
    ]);

    const sendingSessions = markSendingSessionState({}, currentSession.key, "shiori");
    const merged = mergeIncomingSessionDuringSend(
      currentSession,
      incomingSession,
      Boolean(sendingSessions[currentSession.key]),
    );

    assert.deepEqual(merged?.messages, currentSession.messages);
  });
});

describe("clearSendingSessionState", () => {
  it("removes only the finished session from the sending map", () => {
    assert.deepEqual(
      clearSendingSessionState(
        {
          "role:shiori": "shiori",
          "role:other": "other",
        },
        "role:shiori",
      ),
      {
        "role:other": "other",
      },
    );
  });
});

describe("clearAllSendingSessionsState", () => {
  it("clears the sending map once bridge sending state is reset", () => {
    assert.deepEqual(
      clearAllSendingSessionsState({
        "role:shiori": "shiori",
      }),
      {},
    );
  });
});

describe("canSendSessionState", () => {
  it("allows sending in a different role session while another role is still replying", () => {
    assert.equal(
      canSendSessionState(
        {
          "role:shiori": "shiori",
        },
        "role:mira",
      ),
      true,
    );
  });

  it("blocks sending only for the in-flight session itself", () => {
    assert.equal(
      canSendSessionState(
        {
          "role:shiori": "shiori",
        },
        "role:shiori",
      ),
      false,
    );
  });
});

describe("desktop paginated session protocol", () => {
  it("adapts an open response to the loaded renderer page", () => {
    const session = parseOpenedSessionPayload({
      session: {
        key: "role:shiori",
        created_at: "2026-07-06T12:00:00+08:00",
        updated_at: "2026-07-06T12:01:00+08:00",
        last_consolidated: 0,
        metadata: { role_id: "shiori" },
      },
      page: {
        messages: [{ id: "role:shiori:7", seq: 7, role: "assistant", content: "最新消息" }],
        limit: 50,
        has_more: true,
        oldest_seq: 0,
        newest_seq: 7,
        total_count: 8,
        before_seq: null,
        next_before_seq: 7,
      },
    });

    assert.deepEqual(session?.messages, [
      { id: "role:shiori:7", seq: 7, role: "assistant", content: "最新消息" },
    ]);
    assert.equal(session?.pagination?.next_before_seq, 7);
  });

  it("merges an incremental message without replacing the currently loaded page", () => {
    const current = createSession([
      { id: "role:shiori:6", seq: 6, role: "user", content: "上一条" },
      { role: "assistant", content: "流式内容", streaming: true, render_id: "stream-1" },
    ]);
    const update = parseSessionMessageUpdatePayload({
      session: {
        key: "role:shiori",
        created_at: current.created_at,
        updated_at: "2026-07-06T12:02:00+08:00",
        last_consolidated: 0,
        metadata: { role_id: "shiori" },
      },
      message: { id: "role:shiori:7", seq: 7, role: "assistant", content: "完整内容" },
    });

    assert.ok(update);
    const merged = mergeSessionSummaryAndMessage(current, update.session, update.message);

    assert.deepEqual(merged.messages, [
      { id: "role:shiori:6", seq: 6, role: "user", content: "上一条" },
      { id: "role:shiori:7", seq: 7, role: "assistant", content: "完整内容", render_id: "stream-1" },
    ]);
  });

  it("merges every message appended by an external channel turn", () => {
    const current = createSession([
      { id: "role:shiori:5", seq: 5, role: "assistant", content: "上一条" },
    ]);
    current.pagination = {
      limit: 50,
      has_more: false,
      oldest_seq: 5,
      newest_seq: 5,
      total_count: 1,
      before_seq: null,
      next_before_seq: null,
    };
    const update = parseSessionMessageUpdatePayload({
      session: {
        key: current.key,
        created_at: current.created_at,
        updated_at: "2026-07-06T12:03:00+08:00",
        last_consolidated: 0,
        metadata: { role_id: "shiori" },
      },
      message: { id: "role:shiori:7", seq: 7, role: "assistant", content: "来自渠道的回复" },
      messages: [
        { id: "role:shiori:6", seq: 6, role: "user", content: "来自渠道的问题" },
        { id: "role:shiori:7", seq: 7, role: "assistant", content: "来自渠道的回复" },
      ],
    });

    assert.ok(update);
    const merged = mergeSessionSummaryAndMessage(
      current,
      update.session,
      update.message,
      update.messages,
    );

    assert.deepEqual(merged.messages.map((item) => item.content), [
      "上一条",
      "来自渠道的问题",
      "来自渠道的回复",
    ]);
    assert.equal(merged.pagination?.total_count, 3);
  });

  it("replaces an optimistic user message after the bridge confirms its client message id", () => {
    const current = createSession([
      {
        role: "user",
        content: "刚发出去的消息",
        metadata: { client_message_id: "client-message-1" },
      },
    ]);
    current.pagination = {
      limit: 50,
      has_more: true,
      oldest_seq: 0,
      newest_seq: 0,
      total_count: 1,
      before_seq: null,
      next_before_seq: 0,
    };
    const merged = mergeSessionSummaryAndMessage(current, {
      key: current.key,
      created_at: current.created_at,
      updated_at: current.updated_at,
      last_consolidated: current.last_consolidated,
      metadata: current.metadata,
    }, {
      id: "role:shiori:7",
      seq: 7,
      role: "user",
      content: "刚发出去的消息",
      metadata: { client_message_id: "client-message-1" },
    });

    assert.deepEqual(merged.messages, [{
      id: "role:shiori:7",
      seq: 7,
      role: "user",
      content: "刚发出去的消息",
      metadata: { client_message_id: "client-message-1" },
    }]);
    assert.equal(merged.pagination?.total_count, 2);
  });

  it("merges an older sparse-sequence page without losing the streamed tail", () => {
    const current = createSession([
      { id: "role:shiori:8", seq: 8, role: "user", content: "最新" },
      { role: "assistant", content: "正在生成", streaming: true, render_id: "stream-1" },
    ]);
    current.pagination = {
      limit: 2,
      has_more: true,
      oldest_seq: 8,
      newest_seq: 8,
      total_count: 4,
      before_seq: null,
      next_before_seq: 8,
    };

    const merged = mergeSessionMessagePage(current, {
      messages: [
        { id: "role:shiori:0", seq: 0, role: "assistant", content: "最早" },
        { id: "role:shiori:5", seq: 5, role: "user", content: "中间" },
      ],
      limit: 2,
      has_more: false,
      oldest_seq: 0,
      newest_seq: 8,
      total_count: 4,
      before_seq: 8,
      next_before_seq: 0,
    });

    assert.deepEqual(merged.messages.map((message) => message.seq ?? message.render_id), [0, 5, 8, "stream-1"]);
    assert.equal(merged.pagination?.has_more, false);
  });

  it("merges search context by persisted message id without resetting the older-page cursor", () => {
    const current = createSession([{ id: "role:shiori:9", seq: 9, role: "assistant", content: "最新" }]);
    current.pagination = {
      limit: 50,
      has_more: true,
      oldest_seq: 9,
      newest_seq: 9,
      total_count: 10,
      before_seq: null,
      next_before_seq: 9,
    };
    const around = parseSessionMessagesAround({
      session_key: current.key,
      target_message_id: "role:shiori:2",
      messages: [
        { id: "role:shiori:0", seq: 0, role: "user", content: "前文" },
        { id: "role:shiori:2", seq: 2, role: "assistant", content: "命中", is_target: true },
      ],
    });

    assert.ok(around);
    const merged = mergeSessionMessagesAround(current, around);
    assert.deepEqual(merged.messages.map((message) => message.id), ["role:shiori:0", "role:shiori:2", "role:shiori:9"]);
    assert.equal(merged.pagination?.next_before_seq, 9);
  });
});
