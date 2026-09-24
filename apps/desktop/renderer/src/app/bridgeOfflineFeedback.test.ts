/// <reference types="node" />

import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { feedback, getFeedbackSnapshot, resetFeedback, setFeedbackFilter } from "../shared/feedback/feedbackStore.js";
import { createElement } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness.js";
import { createBridgeFeedbackFilter, isBridgeUnavailableMessage, localizeBridgeMessage, useBridgeOfflineFeedbackFilter } from "./bridgeOfflineFeedback.js";

afterEach(() => resetFeedback());

function install(state: { bannerVisible: boolean; bridgeError: string }) {
  return setFeedbackFilter(createBridgeFeedbackFilter(() => state));
}

describe("bridge offline feedback", () => {
  it("recognizes messages that only restate the bridge being down", () => {
    assert.equal(isBridgeUnavailableMessage("打开会话失败：bridge stopped", ""), true);
    assert.equal(isBridgeUnavailableMessage("角色列表加载失败：bridge exited with code 1", ""), true);
    assert.equal(isBridgeUnavailableMessage("保存失败：Traceback: boom", "Traceback: boom\n  at x"), true);
    assert.equal(isBridgeUnavailableMessage("角色名称不能为空", "bridge stopped"), false);
  });

  it("translates the raw English reasons", () => {
    assert.equal(localizeBridgeMessage("打开会话失败：bridge stopped"), "打开会话失败：本地服务已停止");
    assert.equal(localizeBridgeMessage("x：bridge exited with code 3"), "x：本地服务已退出（代码 3）");
  });

  it("drops the redundant toast while the offline banner is up but keeps unrelated errors", () => {
    const state = { bannerVisible: true, bridgeError: "bridge stopped" };
    install(state);
    feedback.error("打开会话失败：bridge stopped");
    feedback.error("角色名称不能为空");
    assert.deepEqual(getFeedbackSnapshot().map((toast) => toast.message), ["角色名称不能为空"]);
  });

  it("shows bridge failures in Chinese when no banner covers them", () => {
    install({ bannerVisible: false, bridgeError: "" });
    feedback.error("打开会话失败：bridge stopped");
    assert.deepEqual(getFeedbackSnapshot().map((toast) => toast.message), ["打开会话失败：本地服务已停止"]);
  });

  it("leaves success and info messages alone", () => {
    install({ bannerVisible: true, bridgeError: "bridge stopped" });
    feedback.success("连接已恢复");
    assert.equal(getFeedbackSnapshot().length, 1);
  });

  it("stops filtering once the owner removes its filter", () => {
    const remove = install({ bannerVisible: true, bridgeError: "bridge stopped" });
    remove();
    feedback.error("打开会话失败：bridge stopped");
    assert.equal(getFeedbackSnapshot()[0]?.message, "打开会话失败：bridge stopped");
  });

  it("clears an already queued bridge toast once the banner appears", async () => {
    function Probe({ visible }: { visible: boolean }) {
      useBridgeOfflineFeedbackFilter(visible, "bridge stopped");
      return null;
    }
    const view = await mountTestComponent(createElement(Probe, { visible: false }));
    try {
      feedback.error("打开会话失败：bridge stopped");
      feedback.error("角色名称不能为空");
      assert.equal(getFeedbackSnapshot().length, 2);
      await view.render(createElement(Probe, { visible: true }));
      assert.deepEqual(getFeedbackSnapshot().map((toast) => toast.message), ["角色名称不能为空"]);
    } finally { await view.cleanup(); }
  });
});
