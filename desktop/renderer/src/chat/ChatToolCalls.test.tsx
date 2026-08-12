/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatToolCalls } from "./ChatToolCalls";

describe("ChatToolCalls", () => {
  const groups = [{
    text: "",
    reasoning_content: "",
    calls: [{
      call_id: "call-1",
      name: "web_search",
      status: "running",
      arguments: { query: "上海天气" },
      final_arguments: {},
      result: "",
    }],
  }];

  it("shows running tool records expanded during streaming", () => {
    const markup = renderToStaticMarkup(<ChatToolCalls groups={groups} streaming />);

    assert.match(markup, /aria-expanded="true"/);
    assert.match(markup, /1 次工具调用/);
    assert.match(markup, /1 个执行中/);
    assert.match(markup, /web_search/);
    assert.match(markup, /上海天气/);
  });

  it("starts collapsed for persisted history", () => {
    const markup = renderToStaticMarkup(<ChatToolCalls groups={groups} streaming={false} />);

    assert.match(markup, /aria-expanded="false"/);
  });
});
