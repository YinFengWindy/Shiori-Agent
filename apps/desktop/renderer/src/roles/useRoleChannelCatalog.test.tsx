import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { act, useEffect } from "react";
import type { BridgeEvent } from "../../../src/bridge/shared";
import type { ChannelSummary } from "../plugins/pluginBridgeClient";
import { getFeedbackSnapshot, resetFeedback } from "../shared/feedback/feedbackStore";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import type { RoleChannelCatalog } from "./roleChannelCatalog";
import { useRoleChannelCatalog } from "./useRoleChannelCatalog";

function row(name: string, state: ChannelSummary["state"]): ChannelSummary {
  return { name, label: name, contactLabel: null, chatIdLabel: null, chatIdHint: null, pluginId: name, pluginEnabled: state !== "plugin_disabled", state, error: "", status: null };
}

const flush = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

afterEach(() => resetFeedback());

async function mountCatalog(listChannels: () => Promise<ChannelSummary[]>) {
  const listeners = new Set<(event: BridgeEvent) => void>();
  const client = { listChannels };
  let latest: RoleChannelCatalog = null;
  function Probe() {
    const channels = useRoleChannelCatalog(client);
    useEffect(() => { latest = channels; });
    return null;
  }
  const view = await mountTestComponent(<Probe />, { windowGlobals: { miraDesktop: {
    onEvent: (listener: (event: BridgeEvent) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
  } } });
  await flush();
  return {
    view,
    get latest() { return latest; },
    async emit(method: string, payload: Record<string, unknown> = {}) {
      await act(async () => {
        for (const listener of [...listeners]) listener({ id: "e", type: "event", method, payload } as BridgeEvent);
      });
      await flush();
    },
  };
}

test("reloads the channel list when a plugin toggle or config change republishes the runtime", async () => {
  let state: ChannelSummary["state"] = "active";
  let calls = 0;
  const catalog = await mountCatalog(async () => { calls += 1; return [row("qqbot", state)]; });
  try {
    assert.equal(catalog.latest?.[0].state, "active");

    state = "plugin_disabled";
    await catalog.emit("runtime.applied", { changed: true });
    assert.equal(catalog.latest?.[0].state, "plugin_disabled");

    // No-op writes and a dying bridge must not trigger a reload.
    await catalog.emit("runtime.applied", { changed: false });
    await catalog.emit("bridge.exit", { message: "gone" });
    assert.equal(calls, 2);

    state = "active";
    await catalog.emit("bridge.ready");
    assert.equal(catalog.latest?.[0].state, "active");
  } finally {
    await catalog.view.cleanup();
  }
});

test("keeps the last good list and reports a failed reload through feedback", async () => {
  let fail = false;
  const catalog = await mountCatalog(async () => {
    if (fail) throw new Error("bridge offline");
    return [row("qqbot", "not_configured")];
  });
  try {
    fail = true;
    await catalog.emit("runtime.applied", { changed: true });
    assert.equal(catalog.latest?.[0].state, "not_configured");
    assert.deepEqual(getFeedbackSnapshot().map((toast) => [toast.tone, toast.message]), [["error", "渠道列表加载失败：bridge offline"]]);
  } finally {
    await catalog.view.cleanup();
  }
});
