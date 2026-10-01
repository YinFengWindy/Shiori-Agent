import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import type React from "react";
import type { SessionPayload } from "@shiori/plugin-sdk";
import { deferred, mountTestComponent } from "@shiori/plugin-sdk/testing";
import type { BridgeResponse, DesktopApi } from "../../../src/bridge/shared";
import { createFeedbackRecorder } from "../shared/testing/feedbackRecorder";
import { findRetryableChatErrorKey } from "../chat/chatFailedTurn";
import type { DesktopSessionStateArgs } from "./desktopSessionTypes";
import { useDesktopSessionState } from "./useDesktopSessionState";

function session(roleId = "mira"): SessionPayload {
  return {
    key: `role:${roleId}`, created_at: "", updated_at: "", last_consolidated: 0,
    metadata: { role_id: roleId }, messages: [],
  };
}

function response(method: string, payload: BridgeResponse["payload"] = {}, error: BridgeResponse["error"] = null): BridgeResponse {
  return { id: "request", type: "response", method, payload, error };
}

function updateRef<T>(ref: React.MutableRefObject<T>) {
  return (value: React.SetStateAction<T>) => {
    ref.current = typeof value === "function" ? (value as (current: T) => T)(ref.current) : value;
  };
}

async function mountSession() {
  const requests: Array<{
    request: Parameters<DesktopApi["invoke"]>[0];
    result: ReturnType<typeof deferred<BridgeResponse>>;
  }> = [];
  const feedback = createFeedbackRecorder();
  const activeSessionRef: React.MutableRefObject<SessionPayload | null> = { current: session() };
  const activeRoleIdRef = { current: "mira" };
  const sendingSessionsRef = { current: {} as Record<string, string> };
  const cancellingSessionsRef = { current: {} as Record<string, string> };
  const ignore = () => {};
  const args: DesktopSessionStateArgs = {
    activeSessionRef, activeRoleIdRef, sendingSessionsRef, cancellingSessionsRef,
    rolesRef: { current: [] }, roleSessionCacheRef: { current: { mira: session() } },
    mainViewRef: { current: { kind: "chat" } }, unreadCountsRef: { current: {} },
    openRoleRequestIdRef: { current: 0 },
    setActiveSession: updateRef(activeSessionRef), setActiveRoleId: updateRef(activeRoleIdRef),
    setSendingSessions: updateRef(sendingSessionsRef), setCancellingSessions: updateRef(cancellingSessionsRef),
    setRoles: ignore, setUnreadCounts: ignore, setSelectedAvatarAsset: ignore,
    setSelectedChatBackground: ignore, setActiveIllustration: ignore,
    feedback: feedback.reporter, reportSendFailure: (failure) => feedback.reporter.error(failure.message),
    applyRoleSnapshot: (role) => { activeRoleIdRef.current = role.id; },
    buildNavigationEntry: (view, roleId = "") => ({ view, activeRoleId: roleId, settingsSection: "models", settingsSubsection: "" }),
    pushNavigationEntry: ignore, replaceNavigationEntry: ignore,
  };
  let controller!: ReturnType<typeof useDesktopSessionState>;
  function Harness() {
    controller = useDesktopSessionState(args);
    return null;
  }
  const view = await mountTestComponent(null);
  const invoke: DesktopApi["invoke"] = (request) => {
    if (request.method === "roles.list") return Promise.resolve(response(request.method, { roles: [] }));
    const result = deferred<BridgeResponse>();
    requests.push({ request, result });
    return result.promise;
  };
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: { invoke } });
  await view.render(<Harness />);
  return {
    ...view, args, requests, feedback,
    get controller() { return controller; },
    send: () => controller.sendMessage({ content: "hello", attachments: [], replyTarget: null }),
    switchRole(roleId: string) {
      activeRoleIdRef.current = roleId;
      controller.commitActiveSession(session(roleId));
    },
  };
}

describe("useDesktopSessionState", () => {
  it("keeps a late send acknowledgement in the source role cache after switching roles", async () => {
    const view = await mountSession();
    try {
      const sending = view.send();
      const pending = view.requests[0]!;
      view.switchRole("other");
      pending.result.resolve(response("chat.send", {
        session: session(),
        message: { id: "user-1", seq: 1, role: "user", content: "hello", metadata: { client_message_id: pending.request.payload.client_message_id } },
      }));
      assert.equal(await sending, true);
      assert.equal(view.args.activeSessionRef.current?.key, "role:other");
      assert.deepEqual(view.args.roleSessionCacheRef.current.mira?.messages.map((message) => message.id), ["user-1"]);
    } finally { await view.cleanup(); }
  });

  it("keeps a cancellation acknowledgement in the source role cache after switching roles", async () => {
    const view = await mountSession();
    try {
      const sending = view.send();
      const pendingSend = view.requests[0]!;
      pendingSend.result.resolve(response("chat.send", { session: session(), message: { id: "user-1", role: "user", content: "hello" } }));
      await sending;
      const cancelling = view.controller.cancelChatTurn("role:mira", "mira");
      view.switchRole("other");
      view.requests[1]!.result.resolve(response("chat.cancel", {
        status: "interrupted", session: session(),
        message_payload: { id: "assistant-1", role: "assistant", content: "partial", metadata: { turn_id: pendingSend.request.payload.turn_id } },
      }));
      assert.equal(await cancelling, true);
      assert.equal(view.args.activeSessionRef.current?.key, "role:other");
      assert.equal(view.args.roleSessionCacheRef.current.mira?.messages.at(-1)?.id, "assistant-1");
      assert.deepEqual(view.args.sendingSessionsRef.current, {});
    } finally { await view.cleanup(); }
  });

  for (const staleRequest of ["chat.send", "chat.cancel", "chat.retry"]) {
    it(`ignores a failed ${staleRequest} response after a new turn takes ownership`, async () => {
      const view = await mountSession();
      try {
        let oldOperation: Promise<boolean>;
        if (staleRequest === "chat.retry") {
          view.controller.commitActiveSession({ ...session(), messages: [
            { id: "u1", role: "user", content: "previous" },
            { role: "error", content: "failed" },
          ] });
          oldOperation = view.controller.retryFailedChatTurn(findRetryableChatErrorKey(view.args.activeSessionRef.current!.messages));
        } else {
          oldOperation = view.send();
        }
        const oldTurnId = String(view.requests[0]!.request.payload.turn_id);
        let oldRequest = view.requests[0]!;
        if (staleRequest === "chat.cancel") {
          oldRequest.result.resolve(response("chat.send", { session: session(), message: { id: "u1", role: "user", content: "hello" } }));
          await oldOperation;
          oldOperation = view.controller.cancelChatTurn("role:mira", "mira");
          oldRequest = view.requests[1]!;
        }
        view.controller.completeChatTurn("role:mira", oldTurnId);
        const nextOperation = view.send();
        const nextRequest = view.requests.at(-1)!;
        const nextTurnId = String(nextRequest.request.payload.turn_id);
        oldRequest.result.resolve(response(staleRequest, {}, { code: "failed", message: "old failure" }));
        assert.equal(await oldOperation, false);
        assert.equal(view.controller.isCurrentChatTurn("role:mira", nextTurnId), true);
        assert.equal(view.args.sendingSessionsRef.current["role:mira"], "mira");
        assert.deepEqual(view.feedback.entries, []);
        assert.equal(view.args.activeSessionRef.current!.messages.at(-1)?.role, "user");
        nextRequest.result.resolve(response("chat.send", { session: session(), message: { id: "u2", role: "user", content: "hello" } }));
        await nextOperation;
      } finally { await view.cleanup(); }
    });
  }

  it("ignores a successful send acknowledgement belonging to an older turn", async () => {
    const view = await mountSession();
    try {
      const oldOperation = view.send();
      const oldRequest = view.requests[0]!;
      view.controller.completeChatTurn("role:mira", String(oldRequest.request.payload.turn_id));
      const nextOperation = view.send();
      const nextRequest = view.requests[1]!;
      const before = view.args.activeSessionRef.current;
      oldRequest.result.resolve(response("chat.send", { session: session(), message: { id: "stale-user", role: "user", content: "stale" } }));
      assert.equal(await oldOperation, true);
      assert.equal(view.args.activeSessionRef.current, before);
      assert.equal(view.controller.isCurrentChatTurn("role:mira", String(nextRequest.request.payload.turn_id)), true);
      nextRequest.result.resolve(response("chat.send", { session: session(), message: { id: "u2", role: "user", content: "hello" } }));
      await nextOperation;
    } finally { await view.cleanup(); }
  });

  it("drops a failed-send recovery snapshot superseded by a bridge reset and a new turn", async () => {
    const view = await mountSession();
    try {
      const oldOperation = view.send();
      await act(async () => view.requests[0]!.result.resolve(response("chat.send", {}, { code: "failed", message: "old failure" })));
      const recovery = view.requests[1]!;
      assert.equal(recovery.request.method, "session.openByRole");
      view.controller.clearAllSendingSessions();
      const nextOperation = view.send();
      const nextRequest = view.requests[2]!;
      const before = view.args.activeSessionRef.current;
      recovery.result.resolve(response("session.openByRole", {
        session: session(), page: { messages: [], limit: 50, has_more: false, oldest_seq: null, newest_seq: null, total_count: 0, before_seq: null, next_before_seq: null },
      }));
      assert.equal(await oldOperation, false);
      assert.equal(view.args.activeSessionRef.current, before);
      assert.equal(view.controller.isCurrentChatTurn("role:mira", String(nextRequest.request.payload.turn_id)), true);
      assert.deepEqual(view.feedback.entries, []);
      nextRequest.result.resolve(response("chat.send", { session: session(), message: { id: "u2", role: "user", content: "hello" } }));
      await nextOperation;
    } finally { await view.cleanup(); }
  });

  it("discards an older role-open response after a newer navigation completes", async () => {
    const view = await mountSession();
    try {
      const first = view.controller.openRole("first");
      const second = view.controller.openRole("second");
      const openPayload = (roleId: string) => ({ session: session(roleId), page: {
        messages: [], limit: 50, has_more: false, oldest_seq: null, newest_seq: null,
        total_count: 0, before_seq: null, next_before_seq: null,
      } });
      view.requests[1]!.result.resolve(response("session.openByRole", openPayload("second")));
      assert.equal(await second, true);
      view.requests[0]!.result.resolve(response("session.openByRole", openPayload("first")));
      assert.equal(await first, false);
      assert.equal(view.args.activeSessionRef.current?.key, "role:second");
      assert.equal(view.args.activeRoleIdRef.current, "second");
    } finally { await view.cleanup(); }
  });
});
