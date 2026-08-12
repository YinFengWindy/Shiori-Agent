/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatThinkingBlock } from "./ChatThinkingBlock";

describe("ChatThinkingBlock", () => {
  it("renders an expanded streaming Thinking trace by default", () => {
    const markup = renderToStaticMarkup(
      <ChatThinkingBlock content="正在分析角色语气" streaming />,
    );

    assert.match(markup, /aria-expanded="true"/);
    assert.match(markup, /chat-thinking-label-streaming/);
    assert.match(markup, /chat-thinking-content-expanded/);
    assert.match(markup, /正在分析角色语气/);
  });

  it("stops the streaming treatment after completion", () => {
    const markup = renderToStaticMarkup(
      <ChatThinkingBlock content="分析完成" streaming={false} />,
    );

    assert.doesNotMatch(markup, /chat-thinking-label-streaming/);
    assert.doesNotMatch(markup, /chat-stream-cursor/);
  });
});
