/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { mergeOpenedSessionSnapshot, mergeSessionMessage, mergeSessionSummaryAndMessage } from "./sessionMessagePagination.js";
import type { SessionMessage, SessionPayload, SessionSummary } from "../shared/types.js";

function createSummary(): SessionSummary {
  return {
    key: "role:mira",
    created_at: "2026-09-07T11:00:00+08:00",
    updated_at: "2026-09-07T11:00:00+08:00",
    last_consolidated: 0,
    metadata: { role_id: "mira" },
  };
}

function createSession(messages: SessionMessage[]): SessionPayload {
  return {
    ...createSummary(),
    messages,
  };
}

describe("mergeSessionSummaryAndMessage", () => {
  it("acknowledges an interrupted turn without consuming the next turn's identical prefix", () => {
    const interrupted: SessionMessage = {
      role: "assistant", content: "晚安<emoji:moon>", render_id: "local:interrupted", streaming: false,
      metadata: { turn_id: "turn-old", interrupted_reply: true },
    };
    const user: SessionMessage = { id: "u2", seq: 3, role: "user", content: "再说一次" };
    const next: SessionMessage = {
      role: "assistant", content: "晚安<emoji:moon>", render_id: "local:next", streaming: true,
      metadata: { turn_id: "turn-next" },
    };
    const committed: SessionMessage = {
      id: "a1", seq: 2, role: "assistant", content: "晚安🌙", reasoning_content: "中断前的思考",
      metadata: { turn_id: "turn-old", interrupted_reply: true },
    };
    const merged = mergeSessionMessage([interrupted, user, next], committed);
    assert.deepEqual(merged, [{ ...committed, render_id: interrupted.render_id }, user, next]);
    assert.deepEqual(mergeSessionMessage(merged, committed), merged);
  });

  it("keeps a failed trace from consuming a later turn's repeated-prefix reply", () => {
    const current: SessionMessage[] = [
      { id: "user-1", seq: 1, role: "user", content: "first" },
      { role: "assistant", content: "hello", render_id: "local:failed", streaming: false, metadata: { streamed_reply: true } },
      { role: "user", content: "next", render_id: "local:user", metadata: { client_message_id: "next" } },
      { role: "assistant", content: "hello there", render_id: "local:active", streaming: true },
    ];
    const merged = mergeSessionMessage(current, { id: "reply", seq: 3, role: "assistant", content: "hello there friend", metadata: { client_message_id: "next" } });
    assert.deepEqual(merged.map((message) => message.render_id ?? message.id), ["user-1", "local:failed", "local:user", "local:active"]);
    assert.equal(merged.at(-1)!.id, "reply");
    assert.equal(merged[1]!.content, "hello");
  });

  it("retains a transient row exactly once across a paginated snapshot roundtrip", () => {
    for (const role of ["error", "user"]) {
      const row = { role, content: "local", render_id: `local:${role}:1` };
      const current = createSession([row]);
      const merged = mergeOpenedSessionSnapshot(current, {
        ...current,
        messages: [{ ...row }],
        pagination: { limit: 80, has_more: false, total_count: 0, oldest_seq: null, newest_seq: null, before_seq: null, next_before_seq: null },
      });
      assert.equal(merged.messages.length, 1);
      assert.equal(merged.messages[0]!.render_id, row.render_id);
    }
  });

  it("keeps optimistic user before a reply arriving before acknowledgement, including later page merges", () => {
    const user = { role: "user", content: "new", render_id: "local:user:1", metadata: { client_message_id: "turn" } };
    const reply = { id: "reply", seq: 3, role: "assistant", content: "reply", metadata: { client_message_id: "turn" } };
    let merged = mergeSessionMessage([user], reply);
    assert.deepEqual(merged.map((message) => message.role), ["user", "assistant"]);
    merged = mergeSessionMessage(merged, { id: "history", seq: 1, role: "assistant", content: "old" });
    merged = mergeSessionMessage(merged, reply);
    assert.deepEqual(merged.map((message) => message.id ?? "local"), ["history", "local", "reply"]);
    merged = mergeSessionMessage(merged, { ...user, id: "user", seq: 2, render_id: undefined });
    assert.deepEqual(merged.map((message) => message.id), ["history", "user", "reply"]);
    assert.equal(merged[1]!.render_id, user.render_id);
  });

  it("keeps distinct persisted assistant rows in the same client turn", () => {
    const first = { id: "a1", seq: 1, role: "assistant", content: "same", metadata: { client_message_id: "turn" } };
    assert.equal(mergeSessionMessage([first], { ...first, id: "a2", seq: 2 }).length, 2);
  });

  it("upgrades a tool-only interrupted reply by call identity without appending a duplicate", () => {
    const transient: SessionMessage = { role: "assistant", content: "", render_id: "local:tool", streaming: true, tool_chain: [{ text: "", reasoning_content: "", calls: [{ call_id: "call", name: "lookup", status: "running", arguments: {}, final_arguments: {}, result: "" }] }] };
    const merged = mergeSessionMessage([transient], { ...transient, id: "interrupted", seq: 1, render_id: undefined, streaming: false, metadata: { interrupted_reply: true } });
    assert.equal(merged.length, 1);
    assert.equal(merged[0]!.render_id, transient.render_id);
  });

  it("keeps the user turn when the assistant reply carries the same client message id", () => {
    const currentSession = createSession([
      {
        id: "role:mira:5",
        seq: 5,
        role: "user",
        content: "刚发出去的消息",
        metadata: { client_message_id: "client-message-1" },
      },
      {
        role: "assistant",
        content: "流式回复",
        streaming: true,
      },
    ]);
    const committedReply: SessionMessage = {
      id: "role:mira:6",
      seq: 6,
      role: "assistant",
      content: "流式回复全文",
      metadata: { client_message_id: "client-message-1", turn_id: "turn-1" },
    };

    const merged = mergeSessionSummaryAndMessage(currentSession, createSummary(), committedReply);

    assert.deepEqual(
      merged.messages.map((message) => [message.role, message.id ?? ""]),
      [
        ["user", "role:mira:5"],
        ["assistant", "role:mira:6"],
      ],
    );
    assert.equal(merged.messages[0]?.content, "刚发出去的消息");
  });

  it("merges a persisted reply with no reasoning_content into the streaming row that already showed thinking (#300)", () => {
    const currentSession = createSession([
      { id: "user-1", seq: 1, role: "user", content: "在吗" },
      { role: "assistant", content: "在的", reasoning_content: "对方好像在等我回复", streaming: true },
    ]);
    const persistedReply: SessionMessage = {
      id: "role:mira:2",
      seq: 2,
      role: "assistant",
      content: "在的，刚看到消息",
      reasoning_content: "",
    };

    const merged = mergeSessionSummaryAndMessage(currentSession, createSummary(), persistedReply);

    // The persisted row must upgrade the existing streaming row, not append a
    // second bubble for the same reply (issue #300).
    assert.equal(merged.messages.length, 2);
    assert.deepEqual(
      merged.messages.map((message) => message.role),
      ["user", "assistant"],
    );
    assert.equal(merged.messages[1]?.id, "role:mira:2");
    assert.equal(merged.messages[1]?.content, "在的，刚看到消息");
  });

  it("replaces the optimistic user turn with its persisted copy by client message id", () => {
    const currentSession = createSession([
      {
        id: "role:mira:4",
        seq: 4,
        role: "assistant",
        content: "上一条回复",
      },
      {
        role: "user",
        content: "刚发出去的消息",
        metadata: { client_message_id: "client-message-1" },
      },
    ]);
    const persistedUserMessage: SessionMessage = {
      id: "role:mira:5",
      seq: 5,
      role: "user",
      content: "刚发出去的消息",
      metadata: { client_message_id: "client-message-1" },
    };

    const merged = mergeSessionSummaryAndMessage(
      currentSession,
      createSummary(),
      persistedUserMessage,
    );

    assert.deepEqual(
      merged.messages.map((message) => [message.role, message.id ?? ""]),
      [
        ["assistant", "role:mira:4"],
        ["user", "role:mira:5"],
      ],
    );
  });
});
