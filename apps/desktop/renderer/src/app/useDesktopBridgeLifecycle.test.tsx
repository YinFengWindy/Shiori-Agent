import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import type { BridgeEvent } from "../../../src/bridge/shared";
import type { SessionPayload } from "../shared/types";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { createFeedbackRecorder } from "../shared/testing/feedbackRecorder";
import { useDesktopBridgeLifecycle } from "./useDesktopBridgeLifecycle";

async function mountLifecycle({ cancelling = false, health = "online" } = {}) {
  let listener!: (event: BridgeEvent) => void;
  const activeSessionRef: React.MutableRefObject<SessionPayload | null> = { current: {
    key: "role:mira", created_at: "", updated_at: "", last_consolidated: 0,
    metadata: {}, messages: [{ id: "user-1", role: "user", content: "hello" }],
  } };
  const completions: string[] = [];
  const statesAtError: SessionPayload[] = [];
  const feedback = createFeedbackRecorder();
  const healthRef = { current: health };
  const healthChanges: string[] = [];
  const invokedMethods: string[] = [];
  const openedRoles: string[] = [];
  const ignore = () => {};
  const args: Parameters<typeof useDesktopBridgeLifecycle>[0] = {
    activeRoleId: "mira", activeIllustration: "",
    setActiveRoleId: ignore, setActiveIllustration: ignore,
    setHealth: (value) => {
      const next = typeof value === "function" ? value(healthRef.current) : value;
      healthRef.current = next;
      healthChanges.push(next);
    },
    setBridgeError: ignore, feedback: feedback.reporter, healthRef,
    setWindowMaximized: ignore, setWindowVisible: ignore,
    setUnreadCounts: ignore,
    activeRoleIdRef: { current: "mira" }, activeSessionRef,
    mainViewRef: { current: { kind: "chat" } }, rolesRef: { current: [] },
    chooseIllustration: () => "", cacheRoleSession: ignore,
    clearAllSendingSessions: ignore, clearSessionSending: ignore,
    completeChatTurn: (_key, turn) => { completions.push(turn); },
    isCurrentChatTurn: (key, turn) => key === "role:mira" && turn === "turn-1" && !completions.includes(turn),
    isChatTurnCancelling: () => cancelling,
    commitActiveSession: (session) => { activeSessionRef.current = session; },
    updateCommittedActiveSession: (update) => { activeSessionRef.current = update(activeSessionRef.current); },
    appendSessionErrorMessage: (_key, message, detail) => {
      const current = activeSessionRef.current;
      assert.ok(current);
      statesAtError.push(current);
      activeSessionRef.current = { ...current, messages: [...current.messages, { role: "error", content: message, ...(detail ? { metadata: { error_detail: detail } } : {}) }] };
    },
    loadRolesFromBridge: async () => [{ id: "mira" } as never],
    openRole: async (roleId) => { openedRoles.push(roleId); return true; },
    buildNavigationEntry: () => ({ view: { kind: "chat" }, activeRoleId: "mira", settingsSection: "models", settingsSubsection: "" }),
    pushNavigationEntry: ignore,
  };
  function Harness() {
    useDesktopBridgeLifecycle(args);
    return null;
  }
  const view = await mountTestComponent(null);
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: {
    onEvent: (callback: typeof listener) => { listener = callback; return ignore; },
    windowState: async () => ({ isMaximized: false, isVisible: true }),
    bridgeStatus: async () => ({ running: true }),
    invoke: async (request: { method: string }) => { invokedMethods.push(request.method); return { error: null, payload: {} }; },
    plugins: undefined,
  } });
  await view.render(<Harness />);
  return {
    ...view, activeSessionRef, completions, statesAtError, feedback, healthRef, healthChanges, invokedMethods, openedRoles,
    async emit(method: string, payload: BridgeEvent["payload"] = {}) {
      await act(async () => listener({ id: "request-1", type: "event", method, payload: {
        session_key: "role:mira", turn_id: "turn-1", ...payload,
      } }));
    },
  };
}

describe("useDesktopBridgeLifecycle", () => {
  for (const doneFirst of [true, false]) it(`replaces an emoji placeholder in the same bubble when done arrives ${doneFirst ? "before" : "after"} persistence`, async () => {
    const view = await mountLifecycle();
    try {
      await view.emit("chat.delta", { thinking_delta: "先道晚安" });
      await view.emit("chat.delta", { content_delta: "晚安。<emoji:moon>" });
      const { messages, ...summary } = view.activeSessionRef.current!;
      const streamed = messages[1]!;
      const committed = {
        id: "assistant-1", seq: 2, role: "assistant", content: "晚安。🌙",
        reasoning_content: "先道晚安，再提醒早点休息",
        metadata: {
          turn_id: "turn-1", client_message_id: "client-1",
          turn_metrics: { total_tokens: 72176, thinking_duration_ms: 1600 },
        },
      };
      if (doneFirst) await view.emit("chat.done", { total_tokens: 70000, thinking_duration_ms: 1500 });
      await view.emit("session.updated", { session: summary, message: committed });
      if (!doneFirst) await view.emit("chat.done", { total_tokens: 70000, thinking_duration_ms: 1500 });

      const replies = view.activeSessionRef.current!.messages.filter((message) => message.role === "assistant");
      assert.equal(replies.length, 1);
      assert.deepEqual(replies[0], { ...committed, render_id: streamed.render_id });
      assert.deepEqual(view.completions, ["turn-1"]);
    } finally { await view.cleanup(); }
  });

  for (const firstEvent of ["chat.delta", "chat.tool.started", "chat.tool.completed"]) {
    it(`reconciles a rewritten media reply after a ${firstEvent} first event`, async () => {
      const view = await mountLifecycle();
      try {
        await view.emit(firstEvent, {
          thinking_delta: "查找合适的图片", iteration: 1, call_id: "call-1", tool_name: "lookup",
          arguments: {}, final_arguments: {}, status: "success", result_preview: "found",
        });
        const first = view.activeSessionRef.current!.messages[1]!;
        assert.equal(first.metadata?.turn_id, "turn-1");
        await view.emit("chat.delta", { content_delta: "<image:night>" });
        await view.emit("chat.done");
        const { messages, ...summary } = view.activeSessionRef.current!;
        assert.equal(messages.length, 2);
        assert.equal(messages[1]?.render_id, first.render_id);
        const committed = {
          id: "assistant-1", seq: 2, role: "assistant", content: "送你一张晚安图。",
          media: ["night.png"], reasoning_content: "选好图片了",
          metadata: { turn_id: "turn-1", client_message_id: "client-1" },
        };
        await view.emit("session.updated", { session: summary, message: committed });
        assert.deepEqual(view.activeSessionRef.current!.messages.slice(1), [{ ...committed, render_id: first.render_id }]);
      } finally { await view.cleanup(); }
    });
  }

  it("reconciles a failed stream before appending its error and releasing the turn", async () => {
    const view = await mountLifecycle();
    try {
      await view.emit("chat.delta", { content_delta: "partial", thinking_delta: "thinking" });
      await view.emit("chat.tool.started", { iteration: 1, call_id: "call-1", tool_name: "web_search", arguments: {} });
      const current = view.activeSessionRef.current!;
      const { messages, ...summary } = current;
      await view.emit("session.updated", {
        session: { ...summary, metadata: { reconciled: true } }, message: messages[0],
      });
      await view.emit("chat.error", { message: "provider failed" });

      const beforeError = view.statesAtError[0]!;
      assert.equal(beforeError.metadata.reconciled, true);
      assert.equal(beforeError.messages[1]?.streaming, false);
      assert.equal(beforeError.messages[1]?.content, "partial");
      assert.equal(beforeError.messages[1]?.reasoning_content, "thinking");
      assert.equal(beforeError.messages[1]?.tool_chain?.[0]?.calls[0]?.status, "error");
      assert.equal(view.activeSessionRef.current?.messages.at(-1)?.role, "error");
      assert.deepEqual(view.feedback.entries, [], "the inline error bubble is the only outlet for a failed turn");
      assert.deepEqual(view.completions, ["turn-1"]);
      await view.emit("chat.delta", { content_delta: "late" });
      assert.equal(view.activeSessionRef.current?.messages.length, 3);
    } finally { await view.cleanup(); }
  });

  it("carries the bridge-reported cause of a failed turn onto its error row", async () => {
    const view = await mountLifecycle();
    try {
      await view.emit("chat.error", { message: "处理消息时出错，请稍后再试。", detail: "APIStatusError: 502 Bad Gateway" });
      assert.equal(view.activeSessionRef.current?.messages.at(-1)?.metadata?.error_detail, "APIStatusError: 502 Bad Gateway");
    } finally { await view.cleanup(); }
  });

  it("ends a stream when the backend cannot supply a snapshot", async () => {
    const view = await mountLifecycle();
    try {
      await view.emit("chat.delta", { content_delta: "partial" });
      await view.emit("chat.error", { message: "provider failed" });
      assert.equal(view.statesAtError[0]?.messages[1]?.streaming, false);
      assert.deepEqual(view.completions, ["turn-1"]);
    } finally { await view.cleanup(); }
  });

  it("ignores foreign errors and leaves cancelling traces to cancellation reconciliation", async () => {
    const view = await mountLifecycle({ cancelling: true });
    try {
      await view.emit("chat.delta", { content_delta: "partial" });
      const streaming = view.activeSessionRef.current;
      await view.emit("chat.error", { session_key: "role:other", message: "foreign" });
      await view.emit("chat.error", { turn_id: "turn-old", message: "stale" });
      assert.deepEqual(view.completions, []);
      await view.emit("chat.error", { message: "cancelled" });
      assert.equal(view.activeSessionRef.current, streaming);
      assert.deepEqual(view.feedback.entries, []);
      assert.deepEqual(view.completions, ["turn-1"]);
    } finally { await view.cleanup(); }
  });

  it("reloads an offline renderer once the main process reports the bridge ready again", async () => {
    const view = await mountLifecycle();
    try {
      view.healthRef.current = "offline";
      view.healthChanges.length = 0;
      view.invokedMethods.length = 0;
      view.openedRoles.length = 0;
      await view.emit("bridge.ready");
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
      assert.deepEqual(view.healthChanges, ["connecting", "online"]);
      assert.equal(view.invokedMethods[0], "health");
      assert.deepEqual(view.openedRoles, ["mira"]);
      assert.deepEqual(view.feedback.messages("success"), ["连接已恢复"]);
    } finally { await view.cleanup(); }
  });

  it("leaves a bridge.ready alone while the renderer is already (re)connecting on its own", async () => {
    const view = await mountLifecycle();
    try {
      view.healthRef.current = "connecting";
      view.healthChanges.length = 0;
      view.invokedMethods.length = 0;
      await view.emit("bridge.ready");
      assert.deepEqual(view.healthChanges, []);
      assert.deepEqual(view.invokedMethods, []);
    } finally { await view.cleanup(); }
  });
});
