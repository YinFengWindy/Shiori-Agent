/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatEmojiPicker } from "./ChatEmojiPicker";

function renderChatEmojiPicker(open: boolean): string {
  return renderToStaticMarkup(
    <ChatEmojiPicker
      disabled={false}
      open={open}
      onClose={() => undefined}
      onSelectEmoji={() => undefined}
      onToggle={() => undefined}
    />,
  );
}

describe("ChatEmojiPicker", () => {
  it("keeps the emoji panel hidden until the toggle is opened", () => {
    const markup = renderChatEmojiPicker(false);

    assert.match(markup, /aria-label="打开常用表情面板"/);
    assert.doesNotMatch(markup, /aria-label="常用表情面板"/);
  });

  it("renders the lightweight emoji grid when opened", () => {
    const markup = renderChatEmojiPicker(true);

    assert.match(markup, /aria-label="收起常用表情面板"/);
    assert.match(markup, /aria-label="常用表情面板"/);
    assert.match(markup, /aria-label="插入表情 😀"/);
    assert.match(markup, /aria-label="插入表情 ❤️"/);
  });
});
