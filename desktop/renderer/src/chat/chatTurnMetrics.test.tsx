/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatReplyMetrics } from "./ChatReplyMetrics";
import { parseChatTurnMetrics } from "./chatTurnMetrics";

describe("chat turn metrics", () => {
  it("rejects null and malformed bridge metrics instead of showing zero usage", () => {
    assert.deepEqual(parseChatTurnMetrics({ total_tokens: null, thinking_duration_ms: "6200" }), {});
  });

  it("shows duration in the footer only when no Thinking block exists", () => {
    const withoutThinking = renderToStaticMarkup(
      <ChatReplyMetrics metrics={{ total_tokens: 2438, thinking_duration_ms: 6200 }} hasThinking={false} />,
    );
    const withThinking = renderToStaticMarkup(
      <ChatReplyMetrics metrics={{ total_tokens: 2438, thinking_duration_ms: 6200 }} hasThinking />,
    );

    assert.match(withoutThinking, /Thought for 6\.2s/);
    assert.match(withoutThinking, /2,438 tokens/);
    assert.doesNotMatch(withThinking, /Thought for/);
    assert.match(withThinking, /2,438 tokens/);
  });
});
