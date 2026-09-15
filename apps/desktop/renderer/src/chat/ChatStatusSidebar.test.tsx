/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatStatusSidebar } from "./ChatStatusSidebar";

describe("ChatStatusSidebar", () => {
  it("keeps status content scrollable when the sidebar is too small", () => {
    const markup = renderToStaticMarkup(
      <ChatStatusSidebar
        currentMood="开心"
        moodIllustrationUrl=""
        roleSelfView="一段足够长的角色想法，用来验证窄窗口下内容不会把侧栏底部控件推出容器。"
        relationshipTags={["亲近"]}
        lonelinessValue={72}
      />,
    );

    assert.match(markup, /overflow-y-auto/);
  });
});
