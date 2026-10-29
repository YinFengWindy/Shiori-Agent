/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { AffectionSummary } from "@yinfengwindy/shiori-sdk";
import { ChatStatusSidebar } from "./ChatStatusSidebar";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { affectionUiRegistry } from "../plugins/affectionUiRegistry";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "../plugins/pluginEnabledStateStore";
import { ChatAffectionMeter } from "../../../../../plugins/affection/ui/ChatAffectionMeter";

const affectionSummary: AffectionSummary = { value: 65, stage: "亲密", progress: 0.25, floor: 60 };

describe("ChatStatusSidebar", () => {
  it("renders historical thoughts verbatim alongside mood and relationship tags", () => {
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
        affection={null}
      />,
    );

    assert.match(markup, /role="region" aria-label="当下想法"/);
    assert.ok(markup.includes(thought));
    assert.match(markup, />开心</);
    assert.match(markup, />亲近</);
    assert.match(markup, />安心</);
    assert.match(markup, />期待见面</);
    assert.match(markup, />默契</);
    assert.ok(!markup.includes('data-testid="chat-affection"'));
  });

  it("hides loneliness while the affection plugin is off", () => {
    affectionUiRegistry.registerChat({ pluginId: "affection", Component: ChatAffectionMeter });
    setPluginEnabledSnapshot([{ id: "affection", enabled: false, state: "DISABLED" }]);
    try {
      const markup = renderToStaticMarkup(
        <ChatStatusSidebar currentMood="" moodUpdatedAt="" moodScope="rin|role:rin" moodIllustrationUrl="" roleSelfView=""
          relationshipTags={[]} lonelinessValue={72} affection={affectionSummary} />,
      );
      assert.ok(!markup.includes("寂寞值"));
      assert.ok(!markup.includes('data-testid="chat-affection"'));
    } finally {
      affectionUiRegistry.unregister("affection");
      resetPluginEnabledStateForTests();
    }
  });

  it("leaves the affection meter to the plugin", () => {
    const markup = renderToStaticMarkup(
      <ChatStatusSidebar currentMood="" moodUpdatedAt="" moodScope="rin|role:rin" moodIllustrationUrl="" roleSelfView=""
        relationshipTags={[]} lonelinessValue={0} affection={affectionSummary} />,
    );
    assert.ok(!markup.includes('data-testid="chat-affection"'));
    assert.ok(!markup.includes("亲密"));
  });

  it("mounts the contributed meter and loneliness without printing the affection value", () => {
    affectionUiRegistry.registerChat({ pluginId: "affection", Component: ChatAffectionMeter });
    setPluginEnabledSnapshot([{ id: "affection", enabled: true, state: "ACTIVE" }]);
    try {
      const markup = renderToStaticMarkup(
        <ChatStatusSidebar currentMood="" moodUpdatedAt="" moodScope="rin|role:rin" moodIllustrationUrl="" roleSelfView=""
          relationshipTags={[]} lonelinessValue={72} affection={affectionSummary} />,
      );
      const start = markup.indexOf('data-testid="chat-affection"');
      const block = markup.slice(start, markup.indexOf("寂寞值", start));
      assert.ok(start >= 0);
      assert.match(block, />亲密</);
      assert.match(block, /width:82.5%/);
      assert.ok(!/>[^<]*\d[^<]*</.test(block));
      assert.match(markup.slice(markup.indexOf("寂寞值")), />72</);
    } finally {
      affectionUiRegistry.unregister("affection");
      resetPluginEnabledStateForTests();
    }
  });

  it("replaces the complete thought and mood on turn updates and role switches", async () => {
    const renderState = (currentMood: string, roleSelfView: string) => (
      <ChatStatusSidebar currentMood={currentMood} roleSelfView={roleSelfView} moodUpdatedAt="" moodScope="rin|role:rin"
        moodIllustrationUrl="" relationshipTags={[]} lonelinessValue={37} affection={null} />
    );
    // A loaded roster: this mount reads the enabled state without a bridge.
    setPluginEnabledSnapshot([]);
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
      resetPluginEnabledStateForTests();
    }
  });
});
