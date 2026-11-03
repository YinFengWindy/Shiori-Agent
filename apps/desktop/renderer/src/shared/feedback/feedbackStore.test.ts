import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import {

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
});

it("keeps distinct technical causes when their safe summaries match", () => {
  feedback.error("OSError: first failure");
  feedback.error("TypeError: second failure");
  assert.equal(getFeedbackSnapshot().length, 2);
  feedback.error("OSError: first failure");
  assert.equal(getFeedbackSnapshot().length, 2);
});
