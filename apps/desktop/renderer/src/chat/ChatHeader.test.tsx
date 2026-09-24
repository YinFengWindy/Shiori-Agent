/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatHeader } from "./ChatHeader";

const render = (typing: boolean) => renderToStaticMarkup(
  <ChatHeader activeRole={null} detailRole={null} title="雨宫凛" typing={typing} onOpenRoleDetail={() => undefined} />,
);

describe("ChatHeader", () => {
  it("shows 正在输入… with three brand sparkles while the role replies", () => {
    const markup = render(true);
    assert.match(markup, /role="status"[^>]*data-testid="chat-header-typing"/);
    assert.match(markup, /正在输入…/);
    const sparkles = markup.match(/<span class="chat-typing-sparkles"[^]*?<\/span><\/span>/)?.[0] ?? "";
    assert.equal(sparkles.match(/<svg /g)?.length, 3);
    assert.doesNotMatch(markup, /chat-typing-dots/);
  });

  it("has no typing line otherwise", () => {
    assert.doesNotMatch(render(false), /chat-typing-sparkles|正在输入/);
  });

  it("marks the avatar and name for the role-switch morph", () => {
    const markup = render(false);
    assert.match(markup, /data-chat-header=""/);
    assert.match(markup, /data-vt-part="avatar"/);
    assert.match(markup, /<span[^>]*data-vt-part="name"[^>]*>雨宫凛<\/span>/);
  });
});
