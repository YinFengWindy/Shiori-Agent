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

    assert.match(withoutThinking, /思考 6.2 秒/);
    assert.match(withoutThinking, /2,438 tokens/);
    assert.doesNotMatch(withThinking, /思考 /);
    assert.match(withThinking, /2,438 tokens/);
  });
});

describe("interrupted reply footer", () => {
  it("marks a stopped reply even when it carries no metrics", () => {
    const markup = renderToStaticMarkup(<ChatReplyMetrics metrics={{}} hasThinking={false} interrupted />);
    assert.match(markup, /已中断/);
  });

  it("renders nothing for a finished reply without metrics", () => {
    assert.equal(renderToStaticMarkup(<ChatReplyMetrics metrics={{}} hasThinking={false} />), "");
  });
});
