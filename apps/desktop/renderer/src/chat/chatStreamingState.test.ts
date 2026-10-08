/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { SessionMessage, SessionPayload } from "@yinfengwindy/shiori-sdk";
import {
  applyChatStreamDelta,
  applyChatToolCompleted,
  applyChatToolStarted,
  failChatStream,
  finalizeChatCancellation,
  finishChatStream,
  interruptChatStream,
} from "./chatStreamingState";

function session(): SessionPayload {
  return {
    key: "role:mira",
    created_at: "2026-08-12T12:00:00+08:00",
    updated_at: "2026-08-12T12:00:00+08:00",
    last_consolidated: 0,
    metadata: {},
    messages: [{ id: "user-1", role: "user", content: "你好" }],
  };
}

describe("chat streaming state", () => {
  it("keeps text, thinking, and tool events on their original reply after a picture arrives", () => {
    const started = applyChatStreamDelta(session(), "（看着你", "先听完", "turn-1");
    const original = started.messages[1]!;
    const picture: SessionMessage = {
      id: "picture", seq: 2, role: "assistant", content: "", media: ["afternoon.png"],
      metadata: { proactive: true, turn_id: "turn-1" },
    };
    const interleaved = { ...started, messages: [...started.messages, picture] };
    const text = applyChatStreamDelta(interleaved, "，声音低下来）", "再回答", "turn-1");
    const tool = applyChatToolStarted(text, {
      turnId: "turn-1", iteration: 1, callId: "call-1", toolName: "lookup", arguments: {},
    });
    const completed = applyChatToolCompleted(tool, {
      turnId: "turn-1", iteration: 1, callId: "call-1", toolName: "lookup", arguments: {},
      finalArguments: {}, status: "success", resultPreview: "found",
    });
    for (const updated of [text, tool, completed]) {
      assert.equal(updated.messages.length, 3);
      assert.equal(updated.messages[1]?.render_id, original.render_id);
      assert.equal(updated.messages[1]?.metadata?.turn_id, "turn-1");
      assert.equal(updated.messages[1]?.content, "（看着你，声音低下来）");
      assert.equal(updated.messages[1]?.reasoning_content, "先听完再回答");
      assert.equal(updated.messages[2], picture);
    }
    assert.equal(completed.messages[1]?.tool_chain?.[0]?.calls[0]?.status, "success");
    assert.equal(original.content, "（看着你");
  });

  for (const terminal of ["done", "error", "interrupted", "idle"] as const) {
    it(`ends only its own reply on ${terminal} when a picture follows the last delta`, () => {
      const old = applyChatStreamDelta(session(), "old", "", "turn-old");
      const started = applyChatToolStarted(old, {
        turnId: "turn-1", iteration: 1, callId: "running", toolName: "lookup", arguments: {},
      });
      const streamed = applyChatStreamDelta(started, "reply", "thinking", "turn-1");
      const original = streamed.messages[2]!;
      const picture: SessionMessage = {
        id: "picture", seq: 2, role: "assistant", content: "", media: ["afternoon.png"],
        metadata: { proactive: true, turn_id: "turn-1" },
      };
      const interleaved = { ...streamed, messages: [...streamed.messages, picture] };
      const metrics = { total_tokens: 58627, thinking_duration_ms: 1400 };
      const finished = terminal === "done" ? finishChatStream(interleaved, metrics, "turn-1")
        : terminal === "error" ? failChatStream(interleaved, "turn-1")
          : finalizeChatCancellation(interleaved, terminal, "turn-1");
      const reply = finished.messages[2]!;
      assert.equal(reply.streaming, false);
      assert.equal(reply.render_id, original.render_id);
      assert.equal(reply.content, "reply");
      assert.equal(reply.reasoning_content, "thinking");
      assert.equal(reply.metadata?.interrupted_reply, terminal === "interrupted" ? true : undefined);
      assert.deepEqual(reply.metadata?.turn_metrics, terminal === "done" ? metrics : undefined);
      assert.equal(reply.tool_chain?.[0]?.calls[0]?.status, terminal === "error" ? "error" : "running");
      assert.equal(finished.messages.length, interleaved.messages.length);
      assert.equal(finished.messages[1], old.messages[1]);
      assert.equal(finished.messages[3], picture);
      assert.equal(original.streaming, true);
    });
  }

  it("does not end or append a reply when its turn is already persisted", () => {
    const persisted: SessionMessage = {
      id: "reply", seq: 2, role: "assistant", content: "final",
      metadata: { turn_id: "turn-1", turn_metrics: { total_tokens: 90 } },
    };
    const current = { ...session(), messages: [...session().messages, persisted] };
    for (const finished of [
      finishChatStream(current, { total_tokens: 80 }, "turn-1"),
      failChatStream(current, "turn-1"),
      finalizeChatCancellation(current, "interrupted", "turn-1"),
      finalizeChatCancellation(current, "idle", "turn-1"),
    ]) assert.equal(finished, current);
  });

  it("retains the turn and render identities through text, tools, completion, and cancellation", () => {
    const thinking = applyChatStreamDelta(session(), "", "thinking", "turn-1");
    const started = applyChatToolStarted(thinking, {
      turnId: "turn-1", iteration: 1, callId: "call-1", toolName: "lookup", arguments: {},
    });
    const completed = applyChatToolCompleted(started, {
      turnId: "turn-1", iteration: 1, callId: "call-1", toolName: "lookup", arguments: {},
      finalArguments: {}, status: "success", resultPreview: "found",
    });
    const text = applyChatStreamDelta(completed, "reply", "", "turn-1");
    assert.equal(text.messages.length, 2);
    assert.equal(text.messages[1]?.tool_chain?.[0]?.calls[0]?.status, "success");
    for (const updated of [started, completed, text, finishChatStream(text, {}, "turn-1"), interruptChatStream(text, "turn-1")]) {
      assert.equal(updated.messages[1]?.metadata?.turn_id, "turn-1");
      assert.equal(updated.messages[1]?.render_id, thinking.messages[1]?.render_id);
    }
  });

  it("starts text and tool traces separately from another turn's unfinished assistant", () => {
    const old = applyChatStreamDelta(session(), "old", "old thinking", "turn-old");
    const nextTurns = [
      applyChatStreamDelta(old, "new", "", "turn-new"),
      applyChatToolStarted(old, {
        turnId: "turn-new", iteration: 1, callId: "call-new", toolName: "lookup", arguments: {},
      }),
      applyChatToolCompleted(old, {
        turnId: "turn-new", iteration: 1, callId: "call-new", toolName: "lookup", arguments: {},
        finalArguments: {}, status: "success", resultPreview: "found",
      }),
    ];
    for (const next of nextTurns) {
      assert.equal(next.messages.length, 3);
      assert.equal(next.messages[1], old.messages[1]);
      assert.equal(next.messages[2]?.metadata?.turn_id, "turn-new");
      assert.notEqual(next.messages[2]?.render_id, old.messages[1]?.render_id);
    }
  });

  it("finishes failed text and tool traces before a later persisted reply", () => {
    const streaming = applyChatToolStarted(applyChatStreamDelta(session(), "partial", "thinking"), {
      iteration: 1, callId: "running", toolName: "web_search", arguments: { query: "test" },
    });
    const completed = applyChatToolCompleted(streaming, {
      iteration: 1, callId: "completed", toolName: "read_file", arguments: {},
      finalArguments: {}, status: "success", resultPreview: "result",
    });
    const laterReply = { id: "proactive-1", role: "assistant", content: "proactive" };
    const withLaterReply = { ...completed, messages: [...completed.messages, laterReply] };
    const failed = failChatStream(withLaterReply);
    const trace = failed.messages[1]!;

    assert.equal(trace.streaming, false);
    assert.equal(trace.content, "partial");
    assert.equal(trace.reasoning_content, "thinking");
    assert.equal(trace.render_id, completed.messages[1]?.render_id);
    assert.equal(trace.metadata?.streamed_reply, true);
    assert.deepEqual(trace.tool_chain?.[0]?.calls.map((call) => call.status), ["error", "success"]);
    assert.equal(trace.tool_chain?.[0]?.calls[1], completed.messages[1]?.tool_chain?.[0]?.calls[1]);
    assert.equal(failed.messages[2], laterReply);
    assert.equal(completed.messages[1]?.streaming, true);
    assert.equal(completed.messages[1]?.tool_chain?.[0]?.calls[0]?.status, "running");
    assert.equal(failChatStream(failed), failed);
    const empty = session();
    assert.equal(failChatStream(empty), empty);
  });

  it("merges Thinking and content deltas into one transient assistant message", () => {
    const original = session();
    const thinking = applyChatStreamDelta(original, "", "先判断语气");
    const content = applyChatStreamDelta(thinking, "你好。", "，再回答");

    assert.equal(original.messages.length, 1);
    assert.deepEqual(content.messages.at(-1), {
      role: "assistant",
      content: "你好。",
      reasoning_content: "先判断语气，再回答",
      streaming: true,
      render_id: content.messages.at(-1)?.render_id,
    });
  });

  it("finishes the transient assistant message without changing its identity", () => {
    const streaming = applyChatStreamDelta(session(), "你好。", "思考");
    const finished = finishChatStream(streaming, {
      total_tokens: 2438,
      thinking_duration_ms: 6200,
    });

    assert.equal(finished.messages.at(-1)?.streaming, false);
    assert.equal(finished.messages.at(-1)?.metadata?.streamed_reply, true);
    assert.deepEqual(finished.messages.at(-1)?.metadata?.turn_metrics, {
      total_tokens: 2438,
      thinking_duration_ms: 6200,
    });
    assert.equal(finished.messages.at(-1)?.render_id, streaming.messages.at(-1)?.render_id);
  });

  it("marks a cancelled transient assistant reply for local trace preservation", () => {
    const streaming = applyChatStreamDelta(session(), "partial answer", "partial thinking");
    const interrupted = interruptChatStream(streaming);

    assert.equal(interrupted.messages.at(-1)?.streaming, false);
    assert.deepEqual(interrupted.messages.at(-1)?.metadata, {
      streamed_reply: true,
      interrupted_reply: true,
    });
    assert.equal(interrupted.messages.at(-1)?.reasoning_content, "partial thinking");
    assert.equal(interrupted.messages.at(-1)?.render_id, streaming.messages.at(-1)?.render_id);
  });

  it("keeps a naturally completed reply distinct when cancellation reports idle", () => {
    const streaming = applyChatStreamDelta(session(), "complete answer", "complete thinking");
    const completed = finalizeChatCancellation(streaming, "idle");

    assert.equal(completed.messages.at(-1)?.streaming, false);
    assert.equal(completed.messages.at(-1)?.metadata?.streamed_reply, true);
    assert.equal(completed.messages.at(-1)?.metadata?.interrupted_reply, undefined);
  });

  it("marks the reply interrupted only when cancellation interrupted the active turn", () => {
    const streaming = applyChatStreamDelta(session(), "partial answer", "partial thinking");
    const interrupted = finalizeChatCancellation(streaming, "interrupted");

    assert.equal(interrupted.messages.at(-1)?.metadata?.interrupted_reply, true);
  });

  it("does not alter an already finished or non-assistant session", () => {
    const original = session();
    assert.equal(interruptChatStream(original), original);
    const finished = finishChatStream(
      applyChatStreamDelta(original, "complete", "thinking"),
    );
    assert.equal(interruptChatStream(finished), finished);
  });

  it("merges tool lifecycle events by call id into the transient assistant message", () => {
    const started = applyChatToolStarted(session(), {
      iteration: 1,
      callId: "call-1",
      toolName: "web_search",
      arguments: { query: "天气" },
    });
    const completed = applyChatToolCompleted(started, {
      iteration: 1,
      callId: "call-1",
      toolName: "web_search",
      arguments: { query: "天气" },
      finalArguments: { query: "上海天气" },
      status: "success",
      resultPreview: "晴，28°C",
    });

    assert.deepEqual(completed.messages.at(-1)?.tool_chain, [{
      text: "",
      reasoning_content: "",
      calls: [{
        call_id: "call-1",
        name: "web_search",
        status: "success",
        arguments: { query: "天气" },
        final_arguments: { query: "上海天气" },
        result: "晴，28°C",
      }],
    }]);
    assert.equal(completed.messages.at(-1)?.streaming, true);
  });

  it("starts a new assistant trace after the previous streamed reply has finished", () => {
    const previousReply = finishChatStream(
      applyChatStreamDelta(session(), "上一轮回复", "上一轮思考"),
    );

    const nextTurn = applyChatToolStarted(previousReply, {
      iteration: 1,
      callId: "call-next-turn",
      toolName: "web_search",
      arguments: { query: "新一轮" },
    });

    assert.equal(nextTurn.messages.length, 3);
    assert.equal(nextTurn.messages[1]?.content, "上一轮回复");
    assert.equal(nextTurn.messages[1]?.streaming, false);
    assert.equal(nextTurn.messages[1]?.tool_chain, undefined);
    assert.deepEqual(nextTurn.messages[2]?.tool_chain?.[0]?.calls?.[0]?.call_id, "call-next-turn");
    assert.equal(nextTurn.messages[2]?.streaming, true);

    const nextTextTurn = applyChatStreamDelta(previousReply, "新一轮文本", "");
    assert.equal(nextTextTurn.messages.length, 3);
    assert.equal(nextTextTurn.messages[1]?.content, "上一轮回复");
    assert.equal(nextTextTurn.messages[2]?.content, "新一轮文本");
    assert.equal(nextTextTurn.messages[2]?.streaming, true);
  });

  it("ignores tool lifecycle events without stable identifiers", () => {
    const original = session();

    const missingCallId = applyChatToolStarted(original, {
      iteration: 1,
      callId: "",
      toolName: "web_search",
      arguments: {},
    });
    const missingToolName = applyChatToolCompleted(original, {
      iteration: 1,
      callId: "call-1",
      toolName: "",
      arguments: {},
      finalArguments: {},
      status: "success",
      resultPreview: "ignored",
    });

    assert.equal(missingCallId, original);
    assert.equal(missingToolName, original);
  });
});
