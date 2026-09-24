/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatStatusSidebar } from "./ChatStatusSidebar";
import { mountTestComponent } from "../shared/testing/domTestHarness";

describe("ChatStatusSidebar", () => {
  it("renders historical thoughts verbatim alongside mood, relationship tags, and loneliness", () => {
    const thought = "我记得窗外的雨慢慢停了，也记得你说今天想早点休息。".repeat(7) + "\n等明天见面，再和你慢慢聊。";
    const markup = renderToStaticMarkup(
      <ChatStatusSidebar
        currentMood="开心"
        moodUpdatedAt=""
        moodScope="rin|role:rin"
        moodIllustrationUrl=""
        roleSelfView={thought}
        relationshipTags={["亲近", "安心", "期待见面", "默契"]}
        lonelinessValue={72}
      />,
    );

    assert.match(markup, /role="region" aria-label="当下想法"/);
    assert.ok(markup.includes(thought));
    assert.match(markup, />开心</);
    assert.match(markup, />亲近</);
    assert.match(markup, />安心</);
    assert.match(markup, />期待见面</);
    assert.match(markup, />默契</);
    assert.match(markup, />72</);
  });

  it("replaces the complete thought and mood on turn updates and role switches", async () => {
    const renderState = (currentMood: string, roleSelfView: string) => (
      <ChatStatusSidebar currentMood={currentMood} roleSelfView={roleSelfView} moodUpdatedAt="" moodScope="rin|role:rin"
        moodIllustrationUrl="" relationshipTags={[]} lonelinessValue={37} />
    );
    const mounted = await mountTestComponent(renderState("平静", "我在等今天的故事。"));
    try {
      for (const [mood, thought] of [
        ["开心", "我听完故事，想把窗边的小花也介绍给你。\n明天还能接着聊。"],
        ["期待", "我刚刚来到这里，还有许多想和你一起了解的事情。"],
      ]) {
        await mounted.render(renderState(mood, thought));
        assert.equal(mounted.container.querySelector('[aria-label="当下想法"]')?.textContent, thought);
        assert.ok(mounted.container.textContent?.includes(mood));
        assert.ok(!mounted.container.textContent?.includes("我在等今天的故事。"));
      }
    } finally {
      await mounted.cleanup();
    }
  });
});
