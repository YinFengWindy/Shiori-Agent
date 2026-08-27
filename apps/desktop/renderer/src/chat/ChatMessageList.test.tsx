/// <reference types="node" />

import React from "react";
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { SessionMessage } from "../shared/types";
import { ChatMessageList } from "./ChatMessageList";
import { getVisibleChatMessages } from "./chatMessageWindow";

describe("ChatMessageList", () => {
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
});
