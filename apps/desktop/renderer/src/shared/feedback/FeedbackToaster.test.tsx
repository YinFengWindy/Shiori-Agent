import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../testing/domTestHarness";
import { appearancePrefsStorageKey } from "../appearancePrefs";
import { mascotFeedback } from "../mascot/mascotFeedback";
import { resetAppearancePrefsCache } from "../useAppearancePrefs";
import { FeedbackToaster } from "./FeedbackToaster";
import { feedback, getFeedbackSnapshot, resetFeedback } from "./feedbackStore";

afterEach(() => {
  resetFeedback();
  resetAppearancePrefsCache();
});

describe("FeedbackToaster", () => {
  it("renders nothing until a message is queued", async () => {
    const view = await mountTestComponent(<FeedbackToaster />);
    try {
      assert.equal(view.container.textContent, "");
      await act(async () => feedback.success("已复制"));
      assert.match(view.container.textContent ?? "", /已复制/);
    } finally { await view.cleanup(); }
  });

  it("announces errors as alerts in their own error styling, not the success one", async () => {
    const view = await mountTestComponent(<FeedbackToaster />);
    try {
      await act(async () => {
        feedback.error("保存失败");
        feedback.success("已保存");
      });
      const error = view.container.querySelector('[data-tone="error"]');
      const success = view.container.querySelector('[data-tone="success"]');
      assert.equal(error?.getAttribute("role"), "alert");
      assert.equal(success?.getAttribute("role"), "status");
      assert.match(error?.innerHTML ?? "", /bg-danger-soft/);
      assert.doesNotMatch(error?.innerHTML ?? "", /bg-success-soft/);
    } finally { await view.cleanup(); }
  });

  it("closes a toast by hand and runs its action once", async () => {
    let selected = 0;
    const view = await mountTestComponent(<FeedbackToaster />);
    try {
      await act(async () => {
        feedback.error("缺少模型", { action: { label: "选择模型", onSelect: () => { selected += 1; } } });
        feedback.info("另一条");
      });
      const buttons = Array.from(view.container.querySelectorAll("button"));
      const action = buttons.find((button) => button.textContent === "选择模型");
      await act(async () => action?.click());
      assert.equal(selected, 1);
      assert.deepEqual(getFeedbackSnapshot().map((toast) => toast.message), ["另一条"]);
      await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="关闭提示"]')?.click());
      assert.deepEqual(getFeedbackSnapshot(), []);
    } finally { await view.cleanup(); }
  });

  it("dismisses a success toast on its own", async () => {
    const view = await mountTestComponent(<FeedbackToaster />);
    try {
      await act(async () => feedback.success("已保存"));
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 2600)); });
      assert.deepEqual(getFeedbackSnapshot(), []);
    } finally { await view.cleanup(); }
  });

  it("lets 吟风 front a persona error: her face, her line first, the message after it, the cause in 详情", async () => {
    resetAppearancePrefsCache();
    const view = await mountTestComponent(<FeedbackToaster />);
    try {
      await act(async () => mascotFeedback.error("角色保存失败", { detail: "Traceback …" }));
      const toast = view.container.querySelector('[data-tone="error"]');
      assert.equal(toast?.getAttribute("data-persona"), "generic");
      assert.equal(toast?.querySelector('[data-testid="mascot-face"]')?.getAttribute("data-expression"), "confused");
      assert.equal(toast?.querySelector(".bg-danger-soft"), null);
      const text = toast?.textContent ?? "";
      assert.ok(text.indexOf("出了点状况") < text.indexOf("角色保存失败"), text);
      assert.doesNotMatch(text, /Traceback/);
      assert.match(text, /详情/);
    } finally { await view.cleanup(); }
  });

  it("fronts a frequent success with her face only, and a milestone with her line too", async () => {
    resetAppearancePrefsCache();
    const view = await mountTestComponent(<FeedbackToaster />);
    try {
      await act(async () => mascotFeedback.success("已复制"));
      const frequent = view.container.querySelector('[data-tone="success"]');
      assert.equal(frequent?.querySelector('[data-testid="mascot-face"]')?.getAttribute("data-expression"), "laugh");
      assert.equal(frequent?.querySelector('[data-testid="feedback-persona-line"]'), null);
      assert.equal(frequent?.textContent, "已复制");
      await act(async () => mascotFeedback.success("角色卡已导入", { persona: "roleImported" }));
      const milestone = Array.from(view.container.querySelectorAll('[data-tone="success"]')).at(-1);
      assert.equal(milestone?.querySelector('[data-testid="mascot-face"]')?.getAttribute("data-expression"), "smug");
      assert.match(milestone?.querySelector('[data-testid="feedback-persona-line"]')?.textContent ?? "", /角色卡读好了/);
      await act(async () => mascotFeedback.info("这张图片已在素材库中"));
      const info = view.container.querySelector('[data-tone="info"]');
      assert.equal(info?.querySelector('[data-testid="mascot-face"]')?.getAttribute("data-expression"), "neutral");
      assert.equal(info?.querySelector('[data-testid="feedback-persona-line"]'), null);
    } finally { await view.cleanup(); }
  });

  it("fronts a warning with her line", async () => {
    resetAppearancePrefsCache();
    const view = await mountTestComponent(<FeedbackToaster />);
    try {
      await act(async () => mascotFeedback.warning("请先创建角色"));
      const toast = view.container.querySelector('[data-tone="warning"]');
      assert.equal(toast?.getAttribute("data-persona"), "warning");
      const text = toast?.textContent ?? "";
      assert.ok(text.indexOf("不对劲") < text.indexOf("请先创建角色"), text);
    } finally { await view.cleanup(); }
  });

  it("renders a persona toast as a plain one with the 看板娘 off", async () => {
    resetAppearancePrefsCache();
    const view = await mountTestComponent(<div />);
    try {
      window.localStorage.setItem(appearancePrefsStorageKey, JSON.stringify({ version: 1, backdropMotion: true, mascot: false }));
      await view.render(<FeedbackToaster />);
      await act(async () => mascotFeedback.error("缺少模型", { persona: "modelMissing" }));
      const toast = view.container.querySelector('[data-tone="error"]');
      assert.equal(toast?.getAttribute("data-persona"), null);
      assert.equal(toast?.querySelector('[data-testid="mascot-face"]'), null);
      assert.match(toast?.innerHTML ?? "", /bg-danger-soft/);
      assert.equal(toast?.textContent?.includes("还没给我接模型"), false);
    } finally { await view.cleanup(); }
  });
});
