import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../testing/domTestHarness";
import { FeedbackToaster } from "./FeedbackToaster";
import { feedback, getFeedbackSnapshot, resetFeedback } from "./feedbackStore";

afterEach(() => resetFeedback());

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
});
