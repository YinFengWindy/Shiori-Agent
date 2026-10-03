import assert from "node:assert/strict";
import { test } from "node:test";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { createFeedbackRecorder } from "../shared/testing/feedbackRecorder";
import { createDesktopChatCancellation } from "./desktopChatCancellation";

test("a rejected cancellation retains its bridge cause while releasing only cancellation state", async () => {
  const feedback = createFeedbackRecorder();
  let cleared = "";
  const view = await mountTestComponent(null, { windowGlobals: { miraDesktop: { invoke: async () => ({
    error: { code: "internal_error", message: "本地服务处理失败", details: { detail: "cancel denied token=private-value" } },
  }) } } });
  const controller = createDesktopChatCancellation({
    feedback: feedback.reporter, latestTurnIdsRef: { current: { "role:mira": "turn-1" } }, cancellingSessionsRef: { current: {} },
    markSessionCancelling: () => undefined, isCurrentChatTurn: () => true,
    clearSessionCancelling: (key) => { cleared = key; },
    completeChatTurn: () => assert.fail("a rejected cancellation cannot complete the turn"),
    updateCommittedActiveSession: () => assert.fail("a rejection cannot replace messages"),
    commitSessionMessageUpdate: () => assert.fail("a rejection cannot commit messages"),
  });
  try {
    assert.equal(await controller.cancelChatTurn("role:mira", "mira"), false);
    assert.equal(cleared, "role:mira");
    assert.match(feedback.messages("error")[0] ?? "", /cancel denied/);
    assert.doesNotMatch(feedback.messages("error")[0] ?? "", /private-value/);
  } finally { await view.cleanup(); }
});
