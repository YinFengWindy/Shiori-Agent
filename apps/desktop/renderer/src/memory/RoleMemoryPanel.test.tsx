import assert from "node:assert/strict";
import { before, it } from "node:test";
import { act } from "react";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "../plugins/pluginEnabledStateStore";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { createPluginRpcTestInvoke } from "../shared/testing/pluginRpcTestBridge";

// Base UI binds DOM globals at import time, so the panel loads inside a test window.
let RoleMemoryPanel: typeof import("./RoleMemoryPanel").RoleMemoryPanel;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ RoleMemoryPanel } = await import("./RoleMemoryPanel"));
  await environment.cleanup();
});

type RuntimeEvent = { method: string; payload: { changed?: boolean } };

/** A desktop bridge whose memory plugin answers with its own id. */
function memoryDesktop() {
  const listeners = new Set<(event: RuntimeEvent) => void>();
  const { invoke, calls } = createPluginRpcTestInvoke((name, params, pluginId) => name === "roles.memory.documents"
    ? { role_id: params.role_id, documents: [] }
    : { role_id: params.role_id, status: "ready", items: [{ id: `${pluginId}-1`, summary: `${pluginId} memory` }], total: 1, page: 1, page_size: 20, filters: {} });
  return {
    calls,
    miraDesktop: {
      invoke,
      onEvent: (listener: (event: RuntimeEvent) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    },
  };
}

it("shows default_memory while it is active and closes when it is not", async () => {
  resetPluginEnabledStateForTests();
  setPluginEnabledSnapshot([{ id: "default_memory", enabled: true, state: "ACTIVE" }]);
  const desktop = memoryDesktop();
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady />, { windowGlobals: { miraDesktop: desktop.miraDesktop } });
  try {
    assert.match(view.container.textContent ?? "", /default_memory memory/);
    assert.deepEqual(desktop.calls.map((call) => call.name).sort(), ["roles.memory.documents", "roles.memory.semantic.list"]);
    assert.ok(desktop.calls.every((call) => call.pluginId === "default_memory"));
    await act(async () => setPluginEnabledSnapshot([{ id: "default_memory", enabled: false, state: "DISABLED" }]));
    assert.match(view.container.textContent ?? "", /记忆已关闭/);
    assert.doesNotMatch(view.container.textContent ?? "", /memory/);
    assert.equal(desktop.calls.length, 2);
  } finally {
    await view.cleanup();
    resetPluginEnabledStateForTests();
  }
});

it("shows loading, not closed, while the plugin roster is still loading", async () => {
  resetPluginEnabledStateForTests();
  const desktop = memoryDesktop();
  const rpcInvoke = desktop.miraDesktop.invoke;
  // The roster request never settles, so the panel stays before its first load.
  const invoke: typeof rpcInvoke = (request) => request.method === "plugins.list" ? new Promise(() => {}) : rpcInvoke(request);
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady />, { windowGlobals: { miraDesktop: { ...desktop.miraDesktop, invoke } } });
  try {
    assert.match(view.container.textContent ?? "", /加载中…/);
    assert.doesNotMatch(view.container.textContent ?? "", /记忆已关闭/);
  } finally {
    await view.cleanup();
    resetPluginEnabledStateForTests();
  }
});

it("shows a disconnected state without reading anything", async () => {
  resetPluginEnabledStateForTests();
  setPluginEnabledSnapshot([{ id: "default_memory", enabled: true, state: "ACTIVE" }]);
  const desktop = memoryDesktop();
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady={false} />, { windowGlobals: { miraDesktop: desktop.miraDesktop } });
  try {
    assert.match(view.container.textContent ?? "", /连接已断开/);
    assert.deepEqual(desktop.calls, []);
  } finally {
    await view.cleanup();
    resetPluginEnabledStateForTests();
  }
});
