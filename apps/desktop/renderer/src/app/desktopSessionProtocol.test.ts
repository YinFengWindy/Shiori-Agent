/// <reference types="node" />
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { SessionMessage, SessionPayload } from "@shiori/plugin-sdk";

import { parseOpenedSessionPayload, parseSessionMessageUpdatePayload } from "./desktopSessionProtocol";
import { mergeSessionSummaryAndMessage } from "./sessionMessagePagination";
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

describe("desktop session protocol", () => {
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
      { role: "assistant", content: "完整", streaming: true, render_id: "stream-1" },
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
});
