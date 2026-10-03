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
  const pending: { method: string; finish: (status: ChatContextStatus) => void }[] = [];
  const listeners = new Set<(event: BridgeEvent) => void>();
  let role = "mira";
  type Props = { bridgeReady: boolean; sending: boolean };
  let props: Props = { bridgeReady: true, sending: false };
  let hook!: ReturnType<typeof useChatContext>;
  function Harness() { hook = useChatContext(role, `role:${role}`, props.bridgeReady, props.sending); return null; }
  const view = await mountTestComponent(null);
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: {
    invoke: ({ method }: { method: string }) => new Promise((resolve) => pending.push({ method, finish: (payload) => resolve({ payload }) })),
    onEvent: (listener: (event: BridgeEvent) => void) => { listeners.add(listener); return () => listeners.delete(listener); },
  } });
  await view.render(<Harness />);
  return { ...view, pending, hook: () => hook,
    async finish(index: number, status = state()) { await act(async () => { pending[index]!.finish(status); }); },
    async switchRole(next: string) { role = next; await view.render(<Harness />); },
    async update(next: Partial<Props>) { props = { ...props, ...next }; await view.render(<Harness />); },
    async emit(method: string) { await act(async () => { for (const listener of listeners) listener({ id: "", type: "event", method, payload: { session_key: `role:${role}` } }); }); },
  };
}

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
