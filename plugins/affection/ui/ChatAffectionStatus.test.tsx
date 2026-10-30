import assert from "node:assert/strict";
import { before, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { BridgeEvent, PluginHostServices, PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { AffectionChatStatus } from "./chatStatus";

// Base UI binds DOM globals at import time, so the block loads inside a test window.
let ChatAffectionStatus: typeof import("./ChatAffectionStatus").ChatAffectionStatus;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ ChatAffectionStatus } = await import("./ChatAffectionStatus"));
  await environment.cleanup();
});

function fakeHost() {
  const listeners = new Set<(event: BridgeEvent) => void>();
  const host = {
    onEvent: (listener: (event: BridgeEvent) => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    ui: { InlineError: ({ message }: { message: string }) => <div>{message}</div> },
  } as unknown as PluginHostServices;
  const emit = (method: string, payload: Record<string, unknown>) => act(async () => {
    for (const listener of listeners) listener({ id: "", type: "event", method, payload });
  });
  return { host, emit };
}

async function mountStatus(answers: AffectionChatStatus[]) {
  const calls: Array<Record<string, unknown>> = [];
  const client = {
    async call(method: string, payload?: Record<string, unknown>) {
      calls.push({ method, ...payload });
      return answers[Math.min(calls.length, answers.length) - 1];
    },
  } as PluginRpcClient;
  const { host, emit } = fakeHost();
  const view = await mountTestComponent(<ChatAffectionStatus roleId="mira" client={client} host={host} />);
  return { view, calls, emit };
}

const first: AffectionChatStatus = {
  role_id: "mira",
  affection: { value: 65, stage: "亲密", progress: 0.25, floor: 60 },
  relation_tags: ["亲近", "安心"],
  loneliness: 72,
};

it("renders the tags, the stage meter and loneliness from its own RPC", async () => {
  const { view, calls } = await mountStatus([first]);
  try {
    assert.deepEqual(calls, [{ method: "chat_status", role_id: "mira" }]);
    const text = view.container.textContent ?? "";
    assert.match(text, /亲近安心/);
    assert.match(text, /好感亲密/);
    assert.match(text, /寂寞值72/);
    assert.ok(!text.includes("关系标签还在生成中"));
  } finally {
    await view.cleanup();
  }
});

it("shows the placeholder before tags exist and no meter before affection is initialized", async () => {
  const { view } = await mountStatus([{ role_id: "mira", affection: null, relation_tags: [], loneliness: 0 }]);
  try {
    const text = view.container.textContent ?? "";
    assert.match(text, /关系标签还在生成中/);
    assert.equal(view.container.querySelector('[data-testid="chat-affection"]'), null);
    assert.match(text, /寂寞值0/);
  } finally {
    await view.cleanup();
  }
});

it("re-reads after its plugin's heartbeat event for its role", async () => {
  const next: AffectionChatStatus = { ...first, loneliness: 80 };
  const { view, calls, emit } = await mountStatus([first, next]);
  try {
    await emit("plugin.affection.chat_status.changed", { role_id: "yin" });
    assert.equal(calls.length, 1);
    await emit("plugin.affection.chat_status.changed", { role_id: "mira" });
    assert.equal(calls.length, 2);
    assert.match(view.container.textContent ?? "", /寂寞值80/);
  } finally {
    await view.cleanup();
  }
});

it("re-reads after a stored turn of its role and ignores other roles", async () => {
  const next: AffectionChatStatus = { ...first, affection: { value: 81, stage: "挚爱", progress: 0.05, floor: 80 }, loneliness: 10 };
  const { view, calls, emit } = await mountStatus([first, next]);
  try {
    await emit("session.updated", { role_id: "yin", session_key: "role:yin" });
    assert.equal(calls.length, 1);
    await emit("session.updated", { role_id: "mira", session_key: "role:mira" });
    assert.equal(calls.length, 2);
    const text = view.container.textContent ?? "";
    assert.match(text, /好感挚爱/);
    assert.match(text, /寂寞值10/);
  } finally {
    await view.cleanup();
  }
});
