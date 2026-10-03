import { strict as assert } from "node:assert";
import test from "node:test";
import type { SessionMessage, SessionPayload } from "@yinfengwindy/shiori-sdk";
import { buildOptimisticUserChatMessage } from "../../renderer/src/chat/chatComposerState";
import { ensureChatMessageRenderId, reconcileSessionMessageRenderIds } from "../../renderer/src/chat/chatMessageIdentity";
import { mergeIncomingSessionDuringSend, shouldClearPendingUserMessage } from "../../renderer/src/chat/chatSessionMerge";
import { applyChatStreamDelta, finalizeChatCancellation, finishChatStream } from "../../renderer/src/chat/chatStreamingState";
import { mergeOpenedSessionSnapshot, mergeSessionSummaryAndMessage } from "../../renderer/src/app/sessionMessagePagination";

const KEY = "role:mira";

function summary() {
  return {
    key: KEY,
    created_at: "2026-09-07T10:00:00+08:00",
    updated_at: "2026-09-07T10:00:00+08:00",
    last_consolidated: 0,
    metadata: {},
  };
}

function persisted(role: "user" | "assistant", seq: number, content: string, cmid?: string): SessionMessage {
  return {
    id: `${KEY}:${seq}`,
    seq,
    role,
    content,
    timestamp: "2026-09-07T10:00:00+08:00",
    media: [],
    metadata: cmid ? { client_message_id: cmid } : {},
  };
}

/** Replays the renderer's session pipeline exactly as useDesktopSessionState composes it. */
class ChatFlowHarness {
  active: SessionPayload | null;
  pending: Record<string, SessionMessage> = {};
  sending: Record<string, string> = {};

  constructor(initial: SessionPayload) {
    this.active = initial;
  }

  commitActiveSession(next: SessionPayload | null): void {
    const incoming = next ? mergeOpenedSessionSnapshot(this.active, next) : null;
    const pendingMessage = incoming ? this.pending[incoming.key] ?? null : null;
    const sending = Boolean(incoming?.key && this.sending[incoming.key]);
    const merged = mergeIncomingSessionDuringSend(this.active, incoming, sending, pendingMessage);
    if (pendingMessage && incoming && shouldClearPendingUserMessage(pendingMessage, incoming, sending)) {
      delete this.pending[incoming.key];
    }
    this.active = reconcileSessionMessageRenderIds(this.active, merged);
  }

  update(updater: (current: SessionPayload | null) => SessionPayload | null): void {
    this.active = updater(this.active);
  }

  send(content: string, cmid: string): void {
    const optimistic = buildOptimisticUserChatMessage(content, [], null, cmid);
    this.pending[KEY] = optimistic;
    this.sending[KEY] = "mira";
    this.update((current) => current ? { ...current, messages: [...current.messages, optimistic] } : current);
  }

  response(userSeq: number, content: string, cmid: string): void {
    this.commitActiveSession(
      mergeSessionSummaryAndMessage(this.active, summary(), persisted("user", userSeq, content, cmid)),
    );
  }

  delta(content: string): void {
    this.update((current) => current ? applyChatStreamDelta(current, content, "") : current);
  }

  done(): void {
    this.update((current) => current ? finishChatStream(current) : current);
    delete this.sending[KEY];
  }

  cancelWithoutAcknowledgement(): void {
    this.update((current) => current ? finalizeChatCancellation(current, "interrupted") : current);
    delete this.sending[KEY];
  }

  cancelAcknowledged(assistantSeq: number, content: string): void {
    this.cancelWithoutAcknowledgement();
    this.commitActiveSession(
      mergeSessionSummaryAndMessage(this.active, summary(), persisted("assistant", assistantSeq, content)),
    );
  }

  sessionUpdated(assistantSeq: number, content: string): void {
    this.commitActiveSession(
      mergeSessionSummaryAndMessage(this.active, summary(), persisted("assistant", assistantSeq, content)),
    );
  }

  roles(): string[] {
    return (this.active?.messages ?? []).map((message) => `${message.role}:${String(message.content)}`);
  }
}

function initialSession(): SessionPayload {
  return {
    ...summary(),
    messages: [
      ensureChatMessageRenderId(persisted("user", 1, "第一条")),
      ensureChatMessageRenderId(persisted("assistant", 2, "第一条回复")),
    ],
    pagination: {
      limit: 50,
      has_more: false,
      oldest_seq: 1,
      newest_seq: 2,
      total_count: 2,
      before_seq: null,
      next_before_seq: null,
    },
  };
}

test("two streamed rounds keep user message order", () => {
  const harness = new ChatFlowHarness(initialSession());

  harness.send("第二条", "cm-2");
  harness.response(3, "第二条", "cm-2");
  harness.delta("第二");
  harness.delta("条回复");
  harness.done();
  harness.sessionUpdated(4, "第二条回复");

  harness.send("第三条", "cm-3");
  harness.response(5, "第三条", "cm-3");
  harness.delta("第三条回复");
  harness.done();
  harness.sessionUpdated(6, "第三条回复");

  assert.deepEqual(harness.roles(), [
    "user:第一条",
    "assistant:第一条回复",
    "user:第二条",
    "assistant:第二条回复",
    "user:第三条",
    "assistant:第三条回复",
  ]);
});

test("a round after an acknowledged cancellation keeps user message order", () => {
  const harness = new ChatFlowHarness(initialSession());

  harness.send("第二条", "cm-2");
  harness.response(3, "第二条", "cm-2");
  harness.delta("第二条回复的一半");
  harness.cancelAcknowledged(4, "第二条回复的一半");

  harness.send("第三条", "cm-3");
  harness.response(5, "第三条", "cm-3");
  harness.delta("第三条回复");
  harness.done();
  harness.sessionUpdated(6, "第三条回复");

  assert.deepEqual(harness.roles(), [
    "user:第一条",
    "assistant:第一条回复",
    "user:第二条",
    "assistant:第二条回复的一半",
    "user:第三条",
    "assistant:第三条回复",
  ]);
});

test("an unacknowledged interrupted trace is never duplicated by later merges", () => {
  const harness = new ChatFlowHarness(initialSession());

  harness.send("第二条", "cm-2");
  harness.response(3, "第二条", "cm-2");
  harness.delta("第二条回复的一半");
  harness.cancelWithoutAcknowledgement();

  harness.send("第三条", "cm-3");
  harness.response(5, "第三条", "cm-3");
  harness.delta("第三条回复");
  harness.done();
  harness.sessionUpdated(6, "第三条回复");

  const contents = harness.roles();
  assert.deepEqual([...new Set(contents)].sort(), [...contents].sort());
  assert.ok(contents.includes("user:第三条"));
  assert.ok(contents.includes("assistant:第二条回复的一半"));
});
