import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { mascotFeedback } from "../mascot/mascotFeedback";
import {
  createFeedbackReporter,
  dismissFeedback,
  feedback,
  getFeedbackSnapshot,
  maxVisibleFeedback,
  resetFeedback,
  showFeedback,
  subscribeFeedback,
} from "./feedbackStore";

afterEach(() => resetFeedback());

describe("feedbackStore", () => {
  it("queues messages oldest first with their tone", () => {
    feedback.success("已保存");
    feedback.error("保存失败");
    assert.deepEqual(getFeedbackSnapshot().map(({ tone, message }) => [tone, message]), [
      ["success", "已保存"],
      ["error", "保存失败"],
    ]);
  });

  it("ignores empty messages instead of rendering a blank toast", () => {
    assert.equal(showFeedback({ tone: "error", message: "   " }), 0);
    assert.deepEqual(getFeedbackSnapshot(), []);
  });

  it("collapses a repeated tone + message into one toast with a fresh id at the end", () => {
    const first = showFeedback({ tone: "error", message: "连接失败" });
    feedback.info("其他");
    const repeated = showFeedback({ tone: "error", message: "连接失败" });
    const snapshot = getFeedbackSnapshot();
    assert.deepEqual(snapshot.map((toast) => toast.message), ["其他", "连接失败"]);
    assert.notEqual(repeated, first);
    assert.equal(snapshot.at(-1)?.id, repeated);
  });

  it("keeps the same message in different tones apart", () => {
    feedback.success("完成");
    feedback.info("完成");
    assert.equal(getFeedbackSnapshot().length, 2);
  });

  it("drops the oldest message beyond the visible limit", () => {
    for (let index = 0; index <= maxVisibleFeedback; index += 1) feedback.info(`消息 ${index}`);
    const messages = getFeedbackSnapshot().map((toast) => toast.message);
    assert.equal(messages.length, maxVisibleFeedback);
    assert.equal(messages[0], "消息 1");
  });

  it("dismisses by id and tolerates unknown ids without notifying", () => {
    const id = showFeedback({ tone: "warning", message: "注意" });
    let notifications = 0;
    const unsubscribe = subscribeFeedback(() => { notifications += 1; });
    dismissFeedback(id + 100);
    assert.equal(notifications, 0);
    dismissFeedback(id);
    assert.equal(notifications, 1);
    assert.deepEqual(getFeedbackSnapshot(), []);
    unsubscribe();
  });

  it("keeps the snapshot reference stable between changes", () => {
    feedback.success("一次");
    const snapshot = getFeedbackSnapshot();
    assert.equal(getFeedbackSnapshot(), snapshot);
  });

  it("carries an optional action through to the queued toast", () => {
    const onSelect = () => undefined;
    feedback.error("缺少模型", { action: { label: "选择模型", onSelect } });
    assert.equal(getFeedbackSnapshot()[0]?.action?.onSelect, onSelect);
  });

  it("starts each call from the reporter's per-tone defaults, which the call's own options override", () => {
    const reporter = createFeedbackReporter({ error: { persona: "generic", detail: "默认详情" } });
    reporter.error("一");
    reporter.error("二", { persona: "modelMissing" });
    reporter.warning("三");
    assert.deepEqual(getFeedbackSnapshot().map(({ message, persona, detail }) => [message, persona, detail]), [
      ["一", "generic", "默认详情"],
      ["二", "modelMissing", "默认详情"],
      ["三", undefined, undefined],
    ]);
  });

  it("has 吟风 front host errors only: the plain reporter and other tones carry no persona", () => {
    mascotFeedback.error("宿主报错");
    mascotFeedback.success("已保存");
    feedback.error("插件报错");
    assert.deepEqual(getFeedbackSnapshot().map(({ message, persona }) => [message, persona]), [
      ["宿主报错", "generic"],
      ["已保存", undefined],
      ["插件报错", undefined],
    ]);
  });
});
