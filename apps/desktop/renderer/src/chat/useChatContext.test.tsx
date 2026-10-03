import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import type { BridgeEvent } from "@yinfengwindy/shiori-sdk";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { useChatContext } from "./useChatContext";
import { notifyChatModelChange } from "./chatModelChanges";
import type { ChatContextStatus } from "./chatContextState";

function state(role = "mira", tokens = 32000): ChatContextStatus {
  return { session_key: `role:${role}`, context_key: "user", model: "model", model_identity: role,
    tokens, source: "local", model_context_window: 128000, input_limit_tokens: 100000,
    can_compact: true, busy: false, reason: "", result: null };
}

async function setup() {
  const pending: { method: string; roleId: string; finish: (status: ChatContextStatus) => void; fail: (error: Error) => void }[] = [];
  const listeners = new Set<(event: BridgeEvent) => void>();
  let role = "mira";
  let sessionKey = "role:mira";
  type Props = { bridgeReady: boolean; sending: boolean };
  let props: Props = { bridgeReady: true, sending: false };
  let hook!: ReturnType<typeof useChatContext>;
  function Harness() {
    hook = useChatContext(role, sessionKey, props.bridgeReady, props.sending);
    return <span>{hook.status?.tokens ?? "正在读取上下文"}</span>;
  }
  const view = await mountTestComponent(null);
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: {
    invoke: ({ method, payload }: { method: string; payload: { role_id: string } }) => new Promise((resolve, reject) => pending.push({ method, roleId: payload.role_id, finish: (payload) => resolve({ payload }), fail: reject })),
    onEvent: (listener: (event: BridgeEvent) => void) => { listeners.add(listener); return () => listeners.delete(listener); },
  } });
  await view.render(<Harness />);
  return { ...view, pending, hook: () => hook,
    async finish(index: number, status = state()) { await act(async () => { pending[index]!.finish(status); }); },
    async fail(index: number) { await act(async () => { pending[index]!.fail(new Error("offline")); }); },
    async switchRole(next: string, nextSession = `role:${next}`) { role = next; sessionKey = nextSession; await view.render(<Harness />); },
    async update(next: Partial<Props>) { props = { ...props, ...next }; await view.render(<Harness />); },
    async emit(method: string, payload: Record<string, unknown> = { session_key: sessionKey }, id = "") {
      await act(async () => { for (const listener of listeners) listener({ id, type: "event", method, payload }); });
    },
  };
}

test("returning to an unchanged role restores its usage without reading it again", async () => {
  const view = await setup();
  try {
    await view.finish(0, state("mira", 123));
    await view.switchRole("other");
    await view.finish(1, state("other", 456));
    await view.switchRole("mira");
    assert.equal(view.hook().status?.tokens, 123);
    assert.equal(view.container.textContent, "123");
    assert.equal(view.pending.length, 2);
  } finally { await view.cleanup(); }
});

test("pending reads are shared across role switches and retain their own session", async () => {
  const view = await setup();
  try {
    await view.switchRole("other");
    await view.switchRole("mira");
    assert.deepEqual(view.pending.map((request) => request.roleId), ["mira", "other"]);
    await view.finish(1, state("other", 456));
    assert.equal(view.hook().status, null);
    await view.finish(0, state("mira", 123));
    assert.equal(view.hook().status?.tokens, 123);
    await view.switchRole("other");
    assert.equal(view.hook().status?.tokens, 456);
    assert.equal(view.pending.length, 2);
  } finally { await view.cleanup(); }
});

test("a context update invalidates an inactive session without rereading the active one", async () => {
  const view = await setup();
  try {
    await view.finish(0, state("mira", 123));
    await view.switchRole("other");
    await view.finish(1, state("other", 456));
    await view.emit("chat.context.updated", { session_key: "role:mira" });
    assert.equal(view.pending.length, 2);
    assert.equal(view.hook().status?.tokens, 456);
    await view.switchRole("mira");
    assert.equal(view.pending.length, 3);
    await view.finish(2, state("mira", 789));
    assert.equal(view.hook().status?.tokens, 789);
  } finally { await view.cleanup(); }
});

for (const method of ["runtime.applied", "plugins.changed", "identities.updated", "roles.updated"]) {
  test(`${method} discards all cached configurations and obsolete reads`, async () => {
    const view = await setup();
    try {
      await view.switchRole("other");
      await view.finish(1, state("other", 456));
      await view.emit(method, {});
      assert.equal(view.hook().status, null);
      await view.finish(0, state("mira", 999));
      await view.finish(2, state("other", 789));
      await view.switchRole("mira");
      assert.equal(view.hook().status, null);
      assert.equal(view.pending.length, 4);
      await view.finish(3, state("mira", 123));
      assert.equal(view.hook().status?.tokens, 123);
    } finally { await view.cleanup(); }
  });
}

test("role updates invalidate only the affected role, including inactive model changes", async () => {
  const view = await setup();
  try {
    await view.finish(0);
    await view.switchRole("other");
    await view.finish(1, state("other", 456));
    await act(async () => notifyChatModelChange("mira", true));
    await view.emit("roles.updated", { role_id: "mira" });
    assert.equal(view.hook().status?.tokens, 456);
    assert.equal(view.pending.length, 2);
    await view.switchRole("mira");
    assert.equal(view.hook().status, null);
    assert.equal(view.hook().notice, "正在切换模型");
    assert.equal(view.pending.length, 2);
    await act(async () => notifyChatModelChange("mira", false));
    await view.finish(2, { ...state("mira", 123), model: "new-model" });
    assert.equal(view.hook().status?.model, "new-model");
  } finally { await view.cleanup(); }
});

test("reconnection invalidates inactive usage and ignores pre-disconnect reads", async () => {
  const view = await setup();
  try {
    await view.finish(0);
    await view.switchRole("other");
    await view.update({ bridgeReady: false });
    await view.finish(1, state("other", 999));
    assert.equal(view.hook().status, null);
    await view.update({ bridgeReady: true });
    await view.finish(2, state("other", 456));
    await view.switchRole("mira");
    assert.equal(view.pending.length, 4);
    await view.finish(3, state("mira", 123));
    assert.equal(view.hook().status?.tokens, 123);
  } finally { await view.cleanup(); }
});

test("the same role's different session keys do not share usage or stale responses", async () => {
  const view = await setup();
  try {
    await view.switchRole("mira", "role:mira:next");
    await view.finish(0, state("mira", 999));
    assert.equal(view.hook().status, null);
    await view.finish(1, { ...state("mira", 123), session_key: "role:mira:next" });
    assert.equal(view.hook().status?.tokens, 123);
    await view.switchRole("mira");
    assert.equal(view.hook().status?.tokens, 999);
    assert.equal(view.pending.length, 2);
  } finally { await view.cleanup(); }
});

for (const id of ["proactive", "proactive:mira"]) {
  test(`${id} message appends invalidate usage but opening metadata does not`, async () => {
    const view = await setup();
    try {
      await view.finish(0);
      await view.switchRole("other");
      await view.finish(1, state("other", 456));
      const payload = { session_key: "role:mira", session: { key: "role:mira" }, change: "metadata_updated" };
      await view.emit("session.updated", payload, id);
      await view.switchRole("mira");
      assert.equal(view.pending.length, 2);
      await view.switchRole("other");
      await view.emit("session.updated", { ...payload, change: "message_appended" }, id);
      assert.equal(view.pending.length, 2);
      await view.switchRole("mira");
      assert.equal(view.pending.length, 3);
      await view.finish(2, state("mira", 123));
      assert.equal(view.hook().status?.tokens, 123);
    } finally { await view.cleanup(); }
  });
}

test("sending defers context reads until the turn ends and completion events share one refresh", async () => {
  const view = await setup();
  try {
    await view.finish(0);
    await view.update({ sending: true });
    await view.emit("chat.context.updated");
    assert.equal(view.pending.length, 1);
    await view.emit("chat.done");
    await view.emit("session.updated", { session_key: "role:mira", session: { key: "role:mira" }, change: "message_appended" }, "desktop-request");
    await view.update({ sending: false });
    assert.equal(view.pending.length, 2);
    await view.finish(1, state("mira", 123));
    assert.equal(view.pending.length, 2);
    assert.equal(view.hook().status?.tokens, 123);
  } finally { await view.cleanup(); }
});

test("a terminal event retries a busy response that was still in flight", async () => {
  const view = await setup();
  try {
    await view.finish(0);
    await view.emit("chat.context.updated");
    await view.emit("chat.done");
    assert.equal(view.pending.length, 2);
    await view.finish(1, { ...state(), tokens: null, busy: true, can_compact: false });
    assert.equal(view.pending.length, 3);
    await view.finish(2, state("mira", 123));
    assert.equal(view.hook().busy, false);
    assert.equal(view.hook().status?.tokens, 123);
  } finally { await view.cleanup(); }
});

for (const transient of ["busy", "unknown", "error", "wrong-session"] as const) {
  test(`${transient} results are retried when returning to the session`, async () => {
    const view = await setup();
    try {
      if (transient === "error") await view.fail(0);
      else await view.finish(0, transient === "wrong-session" ? state("wrong") : {
        ...state(), tokens: null, busy: transient === "busy", model_context_window: null,
      });
      await view.switchRole("other");
      await view.finish(1, state("other", 456));
      await view.switchRole("mira");
      assert.equal(view.pending.length, 3);
      await view.finish(2, state("mira", 123));
      assert.equal(view.hook().status?.tokens, 123);
      assert.equal(view.hook().notice, "");
      assert.equal(view.hook().busy, false);
    } finally { await view.cleanup(); }
  });
}

test("unmount revokes an in-flight terminal retry as well as its status response", async () => {
  const view = await setup();
  try {
    await view.emit("chat.done");
    await view.render(null);
    await view.finish(0, { ...state(), tokens: null, busy: true });
    assert.equal(view.pending.length, 1);
  } finally { await view.cleanup(); }
});

test("role/model changes invalidate already-running status reads", async () => {
  const view = await setup();
  try {
    await view.switchRole("other");
    await view.finish(1, state("other", 100));
    await view.finish(0, state("mira", 999));
    assert.equal(view.hook().status?.tokens, 100);
    await view.emit("chat.context.updated");
    await act(async () => notifyChatModelChange("other", true));
    await view.finish(2, state("other", 999));
    assert.equal(view.hook().status, null);
    await act(async () => notifyChatModelChange("other", false));
    await view.finish(3, state("other", 200));
    assert.equal(view.hook().status?.tokens, 200);
  } finally { await view.cleanup(); }
});

test("a late compact from another role cannot release the new role's busy operation", async () => {
  const view = await setup();
  try {
    await view.finish(0);
    let first!: Promise<void>;
    await act(async () => { first = view.hook().compact(); });
    assert.equal(view.pending[1]!.method, "chat.context.compact");
    await view.switchRole("other");
    await view.finish(2, state("other"));
    let second!: Promise<void>;
    await act(async () => { second = view.hook().compact(); });
    await view.finish(1);
    await first;
    assert.equal(view.hook().busy, true);
    await act(async () => { void view.hook().compact(); });
    assert.equal(view.pending.length, 4);
    await view.finish(3, { ...state("other"), result: { committed: false, memory_committed: true, before_tokens: 32000, after_tokens: null, retained_turns: 2, failure_stage: "summary", error: "offline" } });
    await view.finish(4, state("other"));
    await second;
    assert.equal(view.hook().busy, false);
    assert.match(view.hook().notice, /记忆已整理、压缩失败/);
  } finally { await view.cleanup(); }
});

test("model changes during compaction refresh the current model after the old operation completes", async () => {
  const view = await setup();
  try {
    await view.finish(0);
    let compact!: Promise<void>;
    await act(async () => { compact = view.hook().compact(); });
    await act(async () => notifyChatModelChange("mira", true));
    await act(async () => notifyChatModelChange("mira", false));
    await view.finish(2, { ...state(), model: "new-model", busy: true, can_compact: false, reason: "正在压缩" });
    await view.emit("chat.context.updated");
    assert.equal(view.pending.length, 3);
    await view.finish(1, { ...state("mira", 100), model: "old-model" });
    assert.equal(view.hook().status?.model, "new-model");
    assert.equal(view.pending[3]?.method, "chat.context.status");
    await view.finish(3, { ...state("mira", 200), model: "new-model" });
    await compact;
    assert.equal(view.hook().status?.tokens, 200);
    assert.equal(view.hook().status?.model, "new-model");
    assert.equal(view.hook().busy, false);
  } finally { await view.cleanup(); }
});

test("unmount invalidates compaction ownership before its completion can refresh", async () => {
  const view = await setup();
  try {
    await view.finish(0);
    let compact!: Promise<void>;
    await act(async () => { compact = view.hook().compact(); });
    await view.render(null);
    await view.finish(1);
    await compact;
    assert.equal(view.pending.length, 2);
  } finally { await view.cleanup(); }
});

test("compaction completion waits for reconnection before refreshing usage", async () => {
  const view = await setup();
  try {
    await view.finish(0);
    let compact!: Promise<void>;
    await act(async () => { compact = view.hook().compact(); });
    await view.update({ bridgeReady: false });
    await view.finish(1, { ...state("mira", 8000), result: { committed: true, memory_committed: true, before_tokens: 32000, after_tokens: 8000, retained_turns: 2, failure_stage: "", error: "" } });
    assert.equal(view.pending.length, 2);
    await compact;
    assert.match(view.hook().notice, /上下文已压缩/);
    await view.update({ bridgeReady: true });
    await view.finish(2, state("mira", 8000));
    assert.equal(view.hook().status?.tokens, 8000);
  } finally { await view.cleanup(); }
});

test("a turn refreshes once from the host context event, not from its completion events", async () => {
  const view = await setup();
  try {
    await view.finish(0);
    for (const method of ["chat.done", "chat.error", "session.updated"]) await view.emit(method);
    assert.equal(view.pending.length, 1);
    for (const method of ["chat.context.updated", "runtime.applied"]) {
      await view.emit(method);
      const index: number = view.pending.length - 1;
      assert.equal(view.pending[index]!.method, "chat.context.status");
      await view.finish(index);
    }
  } finally { await view.cleanup(); }
});

test("a running compaction still reports after sending and bridge reconnection, keeping the last usage", async () => {
  const view = await setup();
  try {
    await view.finish(0);
    let compact!: Promise<void>;
    await act(async () => { compact = view.hook().compact(); });
    await view.update({ sending: true });
    await view.update({ bridgeReady: false });
    await view.update({ bridgeReady: true });
    for (let index = 2; index < view.pending.length; index++) {
      await view.finish(index, { ...state("mira"), tokens: null, model_context_window: null, busy: true, can_compact: false, reason: "正在回复或整理上下文，请稍后重试" });
    }
    assert.equal(view.hook().status?.tokens, 32000);
    assert.equal(view.hook().busy, true);
    await view.update({ sending: false });
    await view.finish(1, { ...state("mira", 8000), result: { committed: true, memory_committed: true, before_tokens: 32000, after_tokens: 8000, retained_turns: 2, failure_stage: "", error: "" } });
    assert.match(view.hook().notice, /上下文已压缩/);
    const last: number = view.pending.length - 1;
    assert.equal(view.pending[last]!.method, "chat.context.status");
    await view.finish(last, state("mira", 8000));
    await compact;
    assert.equal(view.hook().busy, false);
    assert.equal(view.hook().status?.tokens, 8000);
  } finally { await view.cleanup(); }
});

test("a command attempted before context is available gives a readable reason", async () => {
  const view = await setup();
  try {
    await act(async () => { await view.hook().compact(); });
    assert.match(view.hook().notice, /上下文用量未知/);
    assert.equal(view.pending.length, 1);
    await view.finish(0, { ...state(), can_compact: false, reason: "没有可压缩的完整轮次" });
    await act(async () => { await view.hook().compact(); });
    assert.equal(view.hook().notice, "没有可压缩的完整轮次");
    assert.equal(view.pending.length, 1);
  } finally { await view.cleanup(); }
});
