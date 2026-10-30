/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { PluginChatAffectionProps } from "@yinfengwindy/shiori-sdk";
import { ChatStatusSidebar } from "./ChatStatusSidebar";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { affectionUiRegistry } from "../plugins/affectionUiRegistry";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "../plugins/pluginEnabledStateStore";

/** Stands in for the plugin's block: shows which role the slot was given. */
function AffectionBlock({ roleId }: PluginChatAffectionProps) {
  return <div data-testid="affection-block">好感区块:{roleId}</div>;
}

function renderSidebar(roleSelfView: string) {
  return renderToStaticMarkup(
    <ChatStatusSidebar currentMood="开心" moodUpdatedAt="" moodScope="rin|role:rin" moodIllustrationUrl=""
      roleId="rin" roleSelfView={roleSelfView} />,
  );
}

function withAffection<T>(enabled: boolean, run: () => T): T {
  affectionUiRegistry.registerChat({ pluginId: "affection", Component: AffectionBlock });
  setPluginEnabledSnapshot([{ id: "affection", enabled, state: enabled ? "ACTIVE" : "DISABLED" }]);
  try {
    return run();
  } finally {
    affectionUiRegistry.unregister("affection");
    resetPluginEnabledStateForTests();
  }
}

describe("ChatStatusSidebar", () => {
  it("renders historical thoughts verbatim alongside mood", () => {
    const thought = "我记得窗外的雨慢慢停了，也记得你说今天想早点休息。".repeat(7) + "\n等明天见面，再和你慢慢聊。";
    const markup = renderSidebar(thought);

    assert.match(markup, /role="region" aria-label="当下想法"/);
    assert.ok(markup.includes(thought));
    assert.match(markup, />开心</);
  });

  it("mounts the enabled affection plugin's block for the open role", () => {
    const markup = withAffection(true, () => renderSidebar("我在等你回来。"));

    assert.match(markup, /好感区块:rin/);
    assert.ok(markup.includes("我在等你回来。"));
  });

  it("shows nothing of affection while the plugin is off, keeping the core thought", () => {
    const markup = withAffection(false, () => renderSidebar("我在等你回来。"));

    assert.ok(!markup.includes('data-testid="affection-block"'));
    assert.ok(!markup.includes("寂寞值"));
    assert.ok(!markup.includes("关系标签"));
    assert.ok(!markup.includes("好感"));
    assert.ok(markup.includes("我在等你回来。"));
  });

  it("shows nothing of affection when no plugin contributes the slot", () => {
    setPluginEnabledSnapshot([{ id: "affection", enabled: true, state: "ACTIVE" }]);
    try {
      const markup = renderSidebar("");
      assert.ok(!markup.includes("寂寞值"));
      assert.ok(!markup.includes("关系标签"));
      assert.ok(!markup.includes("好感"));
    } finally {
      resetPluginEnabledStateForTests();
    }
  });

  it("replaces the complete thought and mood on turn updates and role switches", async () => {
    const renderState = (currentMood: string, roleSelfView: string) => (
      <ChatStatusSidebar currentMood={currentMood} roleSelfView={roleSelfView} moodUpdatedAt="" moodScope="rin|role:rin"
        moodIllustrationUrl="" roleId="rin" />
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
