/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatComposer } from "./ChatComposer";

function renderChatComposer(): string {
  return renderToStaticMarkup(
    <ChatComposer
      activeRoleId="mira"
      sessionKey="role:mira"
      bridgeReady
      sending={false}
      replyTarget={null}
      onSendMessage={async () => true}
      onClearReplyTarget={() => undefined}
      onJumpToMessage={() => undefined}
    />,
  );
}

describe("ChatComposer", () => {
  it("renders attachment, emoji, and send actions in the desktop composer", () => {
    const markup = renderChatComposer();

    assert.match(markup, /aria-label="添加附件"/);
    assert.match(markup, /aria-label="打开常用表情面板"/);
    assert.match(markup, /aria-label="发送消息"/);
  });

  it("uses a contained text mirror instead of synchronous textarea measurement", () => {
    const markup = renderChatComposer();

    assert.match(markup, /data-chat-composer-mirror=""/);
    assert.match(markup, /contain:layout/);
    assert.doesNotMatch(markup, /field-sizing/);
  });
});
