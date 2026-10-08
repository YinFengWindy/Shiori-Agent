import assert from "node:assert/strict";
import { test } from "node:test";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { createFeedbackRecorder } from "../shared/testing/feedbackRecorder";
import { createDesktopChatCancellation } from "./desktopChatCancellation";
import type { SessionPayload } from "@yinfengwindy/shiori-sdk";

for (const status of ["interrupted", "idle"] as const) {
  test(`an ${status} cancellation ends its own trace behind a picture and preserves another turn`, async () => {
    const feedback = createFeedbackRecorder();
    const own = { role: "assistant", content: "partial", streaming: true, render_id: "own", metadata: { turn_id: "turn-1" } };
    const foreign = { role: "assistant", content: "other", streaming: true, metadata: { turn_id: "turn-other" } };
    const picture = { id: "picture", seq: 2, role: "assistant", content: "", media: ["afternoon.png"], metadata: { proactive: true, turn_id: "turn-1" } };
    const summary = { key: "role:mira", created_at: "", updated_at: "", last_consolidated: 0, metadata: {} };
    let current: SessionPayload | null = { ...summary, messages: [own, foreign, picture] };
    const persisted = { id: "reply", seq: 3, role: "assistant", content: "partial", metadata: { turn_id: "turn-1", interrupted_reply: true } };
    let active = true;
    const committed: string[] = [];
    const view = await mountTestComponent(null, { windowGlobals: { miraDesktop: { invoke: async (request: { payload: unknown }) => {
      assert.deepEqual(request.payload, { session_key: "role:mira", turn_id: "turn-1" });
      return { payload: { status, session: summary, ...(status === "interrupted" ? { message_payload: persisted } : {}) } };
    } } } });
    const controller = createDesktopChatCancellation({
      feedback: feedback.reporter, latestTurnIdsRef: { current: { "role:mira": "turn-1" } }, cancellingSessionsRef: { current: {} },
      markSessionCancelling: () => undefined, isCurrentChatTurn: (_key, turn) => active && turn === "turn-1",
      clearSessionCancelling: () => assert.fail("successful cancellation must complete"),
      completeChatTurn: (_key, turn) => { assert.equal(turn, "turn-1"); active = false; },
      updateCommittedActiveSession: (update) => { current = update(current); },
      commitSessionMessageUpdate: (role, update) => {
        assert.equal(role, "mira");
        assert.equal(current?.messages[0]?.streaming, false);
        assert.deepEqual(update.message, persisted);
        committed.push(update.message!.id!);
      },
    });
    try {
      assert.equal(await controller.cancelChatTurn("role:mira", "mira"), true);
      assert.equal(current?.messages[0]?.streaming, false);
      assert.equal(current?.messages[0]?.render_id, own.render_id);
      assert.equal(current?.messages[0]?.metadata?.interrupted_reply, status === "interrupted" ? true : undefined);
      assert.equal(current?.messages[1], foreign);
      assert.equal(current?.messages[2], picture);
      assert.equal(active, false);
      assert.deepEqual(committed, status === "interrupted" ? ["reply"] : []);
      assert.deepEqual(feedback.entries, []);
    } finally { await view.cleanup(); }
  });
}

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
