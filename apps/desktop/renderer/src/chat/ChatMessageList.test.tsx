/// <reference types="node" />

import React from "react";
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { SessionMessage } from "../shared/types";
import { ChatMessageList } from "./ChatMessageList";
import { getVisibleChatMessages } from "./chatMessageWindow";

describe("ChatMessageList", () => {
  function renderMessage(message: SessionMessage): string {
    return renderToStaticMarkup(
      <ChatMessageList
        activeRole={null}
        conversationEndRef={React.createRef<HTMLDivElement>()}
        conversationListRef={React.createRef<HTMLDivElement>()}
        highlightedMessageKey=""
        visibleMessageWindow={getVisibleChatMessages([message], 10)}
        onBeginAttachmentDrag={() => undefined}
        onExpandOlderMessages={() => undefined}
        onJumpToMessage={() => undefined}
        onOpenContextMenu={() => undefined}
        onOpenImagePreview={() => undefined}
      />,
    );
  }

  it("renders assistant Markdown while preserving user message text", () => {
    const assistantMarkup = renderMessage({
      id: "assistant-markdown",
      role: "assistant",
      content: "**formatted**",
    });
    const userMarkup = renderMessage({
      id: "user-plain-text",
      role: "user",
      content: "**原文**",
    });

    assert.ok(assistantMarkup.includes("<strong>formatted</strong>"));
    assert.ok(userMarkup.includes("**原文**"));
    assert.ok(!userMarkup.includes("<strong>"));
  });

  it("keeps text and Thinking emitted before a tool call visible after the final snapshot", () => {
    const message: SessionMessage = {
      id: "assistant-1",
      role: "assistant",
      content: "已经为你记住了。",
      reasoning_content: "确认记忆写入结果",
      tool_chain: [{
        text: "先给你 5 点点评，再附上改写版自我介绍。",
        reasoning_content: "先分析原稿的问题",
        calls: [{
          call_id: "call-memorize",
          name: "memorize",
          status: "success",
          arguments: { summary: "用户偏好" },
          final_arguments: { summary: "用户偏好" },
          result: "已记住",
        }],
      }],
      metadata: { streamed_reply: true },
    };

    const markup = renderToStaticMarkup(
      <ChatMessageList
        activeRole={null}
        conversationEndRef={React.createRef<HTMLDivElement>()}
        conversationListRef={React.createRef<HTMLDivElement>()}
        highlightedMessageKey=""
        visibleMessageWindow={getVisibleChatMessages([message], 10)}
        onBeginAttachmentDrag={() => undefined}
        onExpandOlderMessages={() => undefined}
        onJumpToMessage={() => undefined}
        onOpenContextMenu={() => undefined}
        onOpenImagePreview={() => undefined}
      />,
    );

    assert.match(markup, /先分析原稿的问题/);
    assert.match(markup, /先给你 5 点点评，再附上改写版自我介绍。/);
    assert.match(markup, /memorize/);
    assert.match(markup, /确认记忆写入结果/);
    assert.match(markup, /已经为你记住了。/);
    assert.ok(
      markup.indexOf("先给你 5 点点评，再附上改写版自我介绍。") < markup.indexOf("memorize"),
    );
    assert.ok(markup.indexOf("memorize") < markup.indexOf("已经为你记住了。"));
  });

  it("mounts a bounded DOM window for a large loaded history", () => {
    const messages = Array.from({ length: 1_000 }, (_value, index): SessionMessage => ({
      id: `message-${index}`,
      role: index % 2 === 0 ? "assistant" : "user",
      content: `message-${index}`,
    }));
    const markup = renderToStaticMarkup(
      <ChatMessageList
        activeRole={null}
        sessionKey="role:mira"
        conversationEndRef={React.createRef<HTMLDivElement>()}
        conversationListRef={React.createRef<HTMLDivElement>()}
        highlightedMessageKey=""
        visibleMessageWindow={{ startIndex: 0, hiddenMessageCount: 0, messages }}
        onBeginAttachmentDrag={() => undefined}
        onExpandOlderMessages={() => undefined}
        onJumpToMessage={() => undefined}
        onOpenContextMenu={() => undefined}
        onOpenImagePreview={() => undefined}
      />,
    );

    assert.ok(!markup.includes('data-message-key="message-0"'));
    assert.ok(markup.includes('data-message-key="message-999"'));
    assert.ok((markup.match(/data-message-key=/g) ?? []).length < 80);
  });

  it("disables browser scroll anchoring while the virtual window changes", () => {
    const markup = renderToStaticMarkup(
      <ChatMessageList
        activeRole={null}
        sessionKey="role:mira"
        conversationEndRef={React.createRef<HTMLDivElement>()}
        conversationListRef={React.createRef<HTMLDivElement>()}
        highlightedMessageKey=""
        visibleMessageWindow={{
          startIndex: 0,
          hiddenMessageCount: 0,
          messages: Array.from({ length: 200 }, (_value, index): SessionMessage => ({
            id: `message-${index}`,
            role: "assistant",
            content: `message-${index}`,
          })),
        }}
        onBeginAttachmentDrag={() => undefined}
        onExpandOlderMessages={() => undefined}
        onJumpToMessage={() => undefined}
        onOpenContextMenu={() => undefined}
        onOpenImagePreview={() => undefined}
      />,
    );

    assert.match(markup, /style="[^"]*overflow-anchor:none[^"]*"/);
  });

  it("does not add a second intrinsic-size virtualization layer to message rows", () => {
    const markup = renderToStaticMarkup(
      <ChatMessageList
        activeRole={null}
        sessionKey="role:mira"
        conversationEndRef={React.createRef<HTMLDivElement>()}
        conversationListRef={React.createRef<HTMLDivElement>()}
        highlightedMessageKey=""
        visibleMessageWindow={getVisibleChatMessages([{
          id: "message-1",
          role: "assistant",
          content: "消息内容",
        }], 10)}
        onBeginAttachmentDrag={() => undefined}
        onExpandOlderMessages={() => undefined}
        onJumpToMessage={() => undefined}
        onOpenContextMenu={() => undefined}
        onOpenImagePreview={() => undefined}
      />,
    );

    assert.doesNotMatch(markup, /content-visibility/);
    assert.doesNotMatch(markup, /contain-intrinsic-size/);
  });
});
