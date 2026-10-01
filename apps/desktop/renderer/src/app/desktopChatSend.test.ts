import assert from "node:assert/strict";
import { test } from "node:test";
import { BridgeError, type SessionPayload } from "@shiori/plugin-sdk";
import { mountTestComponent } from "@shiori/plugin-sdk/testing";
import { createDesktopChatSend } from "./desktopChatSend";

test("a rejected send preserves its diagnostic through failed session recovery", async () => {
  const original: SessionPayload = { key: "role:mira", created_at: "", updated_at: "", last_consolidated: 0, metadata: { role_id: "mira" }, messages: [] };
  const activeSessionRef: { current: SessionPayload | null } = { current: original };
  let reported = "";
  let cached: SessionPayload | null = null;
  let completed = false;
  const view = await mountTestComponent(null, { windowGlobals: { miraDesktop: { invoke: async ({ method }: { method: string }) => {
    if (method === "chat.send") throw new BridgeError("本地服务处理失败", "internal_error", { detail: "send denied token=private-value" });
    return { error: { message: "读取失败", code: "internal_error" } };
  } } } });
  const controller = createDesktopChatSend({
    activeRoleIdRef: { current: "mira" }, activeSessionRef, sendingSessionsRef: { current: {} }, pendingUserMessagesRef: { current: {} }, latestTurnIdsRef: { current: {} },
    reportSendFailure: (failure) => { reported = failure.message; }, markSessionSending: () => undefined,
    isLatestChatTurn: () => true, isCurrentChatTurn: () => true, completeChatTurn: () => { completed = true; },
    updateCommittedActiveSession: (updater) => { activeSessionRef.current = updater(activeSessionRef.current); },
    cacheRoleSession: (_roleId, snapshot) => { cached = snapshot; }, commitSessionMessageUpdate: () => assert.fail("failed send cannot commit a message"),
  });
  try {
    assert.equal(await controller.sendMessage({ content: "hello", attachments: [], replyTarget: null }), false);
    assert.equal(completed, true);
    assert.equal(cached, original);
    assert.match(reported, /send denied/);
    assert.doesNotMatch(reported, /private-value/);
  } finally { await view.cleanup(); }
});
