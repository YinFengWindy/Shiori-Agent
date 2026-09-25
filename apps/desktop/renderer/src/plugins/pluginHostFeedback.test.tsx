import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act } from "react";
import { appearancePrefsStorageKey } from "../shared/appearancePrefs";
import { FeedbackToaster } from "../shared/feedback/FeedbackToaster";
import { getFeedbackSnapshot, resetFeedback } from "../shared/feedback/feedbackStore";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { resetAppearancePrefsCache } from "../shared/useAppearancePrefs";
import { HostInlineError, pluginHostFeedback } from "./pluginHostFeedback";
import { desktopPluginHostServices } from "./pluginHostServices";

afterEach(() => {
  resetFeedback();
  resetAppearancePrefsCache();
});

/** A fresh window with 设置 › 外观 › 看板娘 set to `mascot`. */
async function mountWithMascot(mascot: boolean) {
  const view = await mountTestComponent(null);
  resetAppearancePrefsCache();
  window.localStorage.setItem(appearancePrefsStorageKey, JSON.stringify({ version: 1, backdropMotion: true, mascot }));
  return view;
}

describe("plugin host feedback (runtime API 2.4.0)", () => {
  it("is what the host services hand to plugins", () => {
    assert.equal(desktopPluginHostServices.feedback, pluginHostFeedback);
    assert.equal(desktopPluginHostServices.ui.InlineError, HostInlineError);
  });

  it("queues plain toasts unless the plugin opts in, then applies the host's rule per tone", () => {
    pluginHostFeedback.error("插件报错", { detail: "cause" });
    assert.equal(getFeedbackSnapshot().at(-1)?.persona, undefined);
    resetFeedback();
    pluginHostFeedback.error("插件报错", { persona: true });
    pluginHostFeedback.warning("插件警告", { persona: true });
    pluginHostFeedback.success("插件已保存", { persona: true });
    assert.deepEqual(getFeedbackSnapshot().map(({ message, persona }) => [message, persona]), [
      ["插件报错", "generic"],
      ["插件警告", "warning"],
      ["插件已保存", "success"],
    ]);
    resetFeedback();
    const action = { label: "去设置", onSelect: () => undefined };
    pluginHostFeedback.info("插件提示", { persona: true, action, detail: "细节" });
    const toast = getFeedbackSnapshot().at(-1);
    assert.equal(toast?.persona, "info");
    assert.equal(toast?.action, action);
    assert.equal(toast?.detail, "细节");
  });

  it("shows her on an opted-in plugin toast, and nothing of her with the 看板娘 off", async () => {
    const on = await mountWithMascot(true);
    try {
      await on.render(<FeedbackToaster />);
      await act(async () => pluginHostFeedback.error("生图失败", { persona: true, detail: "timeout" }));
      assert.ok(on.container.querySelector('[data-tone="error"] [data-testid="mascot-face"]'));
    } finally { await on.cleanup(); }
    resetFeedback();
    const off = await mountWithMascot(false);
    try {
      await off.render(<FeedbackToaster />);
      await act(async () => pluginHostFeedback.error("生图失败", { persona: true, detail: "timeout" }));
      const toast = off.container.querySelector('[data-tone="error"]');
      assert.equal(toast?.querySelector('[data-testid="mascot-face"]'), null);
      assert.equal(toast?.querySelector('[data-testid="feedback-persona-line"]'), null);
    } finally { await off.cleanup(); }
  });

  it("gives plugins the host inline error, with her only on persona and never with the 看板娘 off", async () => {
    const on = await mountWithMascot(true);
    try {
      await on.render(<HostInlineError message="加载失败" />);
      assert.equal(on.container.querySelector('[data-testid="mascot-face"]'), null, "persona defaults to off for plugins");
      await on.render(<HostInlineError persona message="加载失败" />);
      assert.ok(on.container.querySelector('[data-testid="mascot-face"]'));
      assert.equal(on.container.querySelector('[role="alert"]')?.getAttribute("data-persona"), "generic");
    } finally { await on.cleanup(); }
    const off = await mountWithMascot(false);
    try {
      await off.render(<HostInlineError persona message="加载失败" />);
      assert.equal(off.container.querySelector('[data-testid="mascot-face"]'), null);
      assert.equal(off.container.querySelector('[role="alert"]')?.textContent, "加载失败");
    } finally { await off.cleanup(); }
  });
});
