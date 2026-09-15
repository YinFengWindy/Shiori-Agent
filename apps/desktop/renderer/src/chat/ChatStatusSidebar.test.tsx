/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatStatusSidebar } from "./ChatStatusSidebar";

describe("ChatStatusSidebar", () => {
  it("keeps the complete thought accessible alongside mood, relationship tags, and loneliness", () => {
    const markup = renderToStaticMarkup(
      <ChatStatusSidebar
        currentMood="开心"
        moodIllustrationUrl=""
        roleSelfView="一段足够长的角色想法，用来验证窄窗口下内容不会把侧栏底部控件推出容器。"
        relationshipTags={["亲近"]}
        lonelinessValue={72}
      />,
    );

    assert.match(markup, /role="region" aria-label="当下想法"/);
    assert.match(markup, /一段足够长的角色想法，用来验证窄窗口下内容不会把侧栏底部控件推出容器。/);
    assert.match(markup, />开心</);
    assert.match(markup, />亲近</);
    assert.match(markup, />72</);
  });
});
