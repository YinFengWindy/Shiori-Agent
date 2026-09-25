import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { getFeedbackSnapshot, resetFeedback, type FeedbackTone } from "../feedback/feedbackStore";
import { feedbackPersonaCue, feedbackTonePersona, mascotFeedback } from "./mascotFeedback";
import { feedbackPersonaLines } from "./mascotLines";

afterEach(() => resetFeedback());

/** What 吟风 shows on a toast `mascotFeedback[tone]` queued with these options. */
function cueFor(tone: FeedbackTone, options?: Parameters<typeof mascotFeedback.error>[1]) {
  resetFeedback();
  mascotFeedback[tone]("消息", options);
  const toast = getFeedbackSnapshot().at(-1);
  assert.ok(toast);
  return feedbackPersonaCue(toast);
}

describe("toast persona rule", () => {
  it("gives errors and warnings a line, and frequent success / info toasts only her face", () => {
    assert.ok(cueFor("error", { detail: "Traceback" })?.text);
    assert.ok(cueFor("warning")?.text);
    const success = cueFor("success");
    const info = cueFor("info");
    assert.deepEqual(success, { expression: "laugh" });
    assert.deepEqual(info, { expression: "neutral" });
    assert.equal(success?.text, undefined);
    assert.equal(info?.text, undefined);
  });

  it("speaks on a success only when the call site names a milestone line", () => {
    assert.equal(cueFor("success", { persona: "roleCreated" }), feedbackPersonaLines.roleCreated);
    assert.ok(feedbackPersonaLines.roleCreated.text);
  });

  it("does not promise a 详情 the error has none of", () => {
    assert.equal(cueFor("error", { detail: "Traceback" }), feedbackPersonaLines.generic);
    assert.equal(cueFor("error"), feedbackPersonaLines.genericBrief);
    assert.doesNotMatch(feedbackPersonaLines.genericBrief.text, /详情/);
  });

  it("leaves a toast without persona plain, and maps every tone to its default", () => {
    assert.equal(feedbackPersonaCue({ persona: undefined }), null);
    assert.deepEqual(feedbackTonePersona, { success: "success", info: "info", warning: "warning", error: "generic" });
  });
});
