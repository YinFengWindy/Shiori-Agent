/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { SessionPayload } from "../shared/types";
import {
  applyChatStreamDelta,
  applyChatToolCompleted,
  applyChatToolStarted,
  finishChatStream,
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
    const finished = finishChatStream(streaming);

    assert.equal(finished.messages.at(-1)?.streaming, false);
    assert.equal(finished.messages.at(-1)?.metadata?.streamed_reply, true);
    assert.equal(finished.messages.at(-1)?.render_id, streaming.messages.at(-1)?.render_id);
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
