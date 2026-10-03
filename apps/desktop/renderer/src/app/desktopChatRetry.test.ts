import assert from "node:assert/strict";
import { test } from "node:test";
import { BridgeError, type SessionPayload } from "@yinfengwindy/shiori-sdk";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { createDesktopChatRetry } from "./desktopChatRetry";

test("a rejected retry restores its error row and retains the RPC diagnostic", async () => {
  const activeSessionRef: { current: SessionPayload | null } = { current: { key: "role:mira", created_at: "", updated_at: "", last_consolidated: 0, metadata: { role_id: "mira" }, messages: [
    { id: "user-1", role: "user", content: "hello" }, { render_id: "error-1", role: "error", content: "原先的失败" },
  ] } };
  let reported = "";
  let restored = "";
  const view = await mountTestComponent(null, { windowGlobals: { miraDesktop: { invoke: async () => {
    throw new BridgeError("本地服务处理失败", "internal_error", { detail: "retry denied token=private-value" });
  } } } });
  const controller = createDesktopChatRetry({
    activeRoleIdRef: { current: "mira" }, activeSessionRef, sendingSessionsRef: { current: {} }, latestTurnIdsRef: { current: {} },
    reportSendFailure: (failure) => { reported = failure.message; }, markSessionSending: () => undefined,
    isCurrentChatTurn: () => true, completeChatTurn: () => undefined,
    updateCommittedActiveSession: (updater) => { activeSessionRef.current = updater(activeSessionRef.current); },
    appendSessionErrorMessage: (_key, content) => { restored = content; },
  });
  try {
    assert.equal(await controller.retryFailedChatTurn("error-1"), false);
    assert.equal(restored, "原先的失败");
    assert.match(reported, /retry denied/);
    assert.doesNotMatch(reported, /private-value/);
  } finally { await view.cleanup(); }
});
