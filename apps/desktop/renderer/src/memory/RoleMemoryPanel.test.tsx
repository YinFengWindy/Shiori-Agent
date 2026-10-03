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

/** A desktop bridge whose memory plugins each answer with their own id. */
function memoryDesktop(readSettings: () => Promise<unknown>) {
  const listeners = new Set<(event: RuntimeEvent) => void>();
  const { invoke, calls } = createPluginRpcTestInvoke((name, params, pluginId) => name === "roles.memory.documents"
    ? { role_id: params.role_id, documents: [] }
    : { role_id: params.role_id, status: "ready", items: [{ id: `${pluginId}-1`, summary: `${pluginId} memory` }], total: 1, page: 1, page_size: 20, filters: {} });
  return {
    calls,
    publish: async (changed: boolean) => { await act(async () => { for (const listener of listeners) listener({ method: "runtime.applied", payload: { changed } }); }); },
    miraDesktop: {
      invoke,
      readSettings,
      onEvent: (listener: (event: RuntimeEvent) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    },
  };
}

it("uses the default plugin namespace and stops reading when it is disabled", async () => {
  resetPluginEnabledStateForTests();
  setPluginEnabledSnapshot([{ id: "default_memory", enabled: true, state: "ACTIVE" }]);
  const desktop = memoryDesktop(async () => ({ formData: { memory: { engine: "default" } } }));
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady />, { windowGlobals: { miraDesktop: desktop.miraDesktop } });
  try {
    assert.match(view.container.textContent ?? "", /default_memory memory/);
    assert.deepEqual(desktop.calls.map((call) => call.name).sort(), ["roles.memory.documents", "roles.memory.semantic.list"]);
    assert.ok(desktop.calls.every((call) => call.pluginId === "default_memory"));
    await act(async () => setPluginEnabledSnapshot([{ id: "default_memory", enabled: false, state: "DISABLED" }]));
    assert.match(view.container.textContent ?? "", /记忆插件不可用/);
    assert.doesNotMatch(view.container.textContent ?? "", /memory/);
    assert.equal(desktop.calls.length, 2);
  } finally {
    await view.cleanup();
    resetPluginEnabledStateForTests();
  }
});

it("is unavailable when the configured plugin is not installed", async () => {
  resetPluginEnabledStateForTests();
  setPluginEnabledSnapshot([{ id: "default_memory", enabled: true, state: "ACTIVE" }]);
  const desktop = memoryDesktop(async () => ({ formData: { memory: { engine: "missing" } } }));
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady />, { windowGlobals: { miraDesktop: desktop.miraDesktop } });
  try {
    assert.match(view.container.textContent ?? "", /记忆插件不可用/);
    assert.deepEqual(desktop.calls, []);
  } finally {
    await view.cleanup();
    resetPluginEnabledStateForTests();
  }
});

it("hides the old engine while a changed runtime read is pending and reports a failed settings read", async () => {
  resetPluginEnabledStateForTests();
  setPluginEnabledSnapshot([{ id: "default_memory", enabled: true, state: "ACTIVE" }]);
  let reads = 0;
  let failNext: ((error: Error) => void) | undefined;
  const desktop = memoryDesktop(() => ++reads === 1
    ? Promise.resolve({ formData: { memory: { engine: "default" } } })
    : new Promise((_, reject) => { failNext = reject; }));
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady />, { windowGlobals: { miraDesktop: desktop.miraDesktop } });
  try {
    assert.match(view.container.textContent ?? "", /default_memory memory/);
    await desktop.publish(false);
    assert.match(view.container.textContent ?? "", /default_memory memory/);
    await desktop.publish(true);
    assert.match(view.container.textContent ?? "", /加载中/);
    assert.doesNotMatch(view.container.textContent ?? "", /default_memory memory/);
    await act(async () => failNext?.(new Error("settings stalled")));
    assert.match(view.container.querySelector('[role="alert"]')?.textContent ?? "", /记忆设置读取失败：settings stalled/);
    assert.doesNotMatch(view.container.textContent ?? "", /default_memory memory/);
  } finally {
    await view.cleanup();
    resetPluginEnabledStateForTests();
  }
});

it("shows loading, not unavailable, while the plugin roster is still loading", async () => {
  resetPluginEnabledStateForTests();
  const desktop = memoryDesktop(async () => ({ formData: { memory: { engine: "default" } } }));
  const rpcInvoke = desktop.miraDesktop.invoke;
  // The roster request never settles, so the panel stays before its first load.
  const invoke: typeof rpcInvoke = (request) => request.method === "plugins.list" ? new Promise(() => {}) : rpcInvoke(request);
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady />, { windowGlobals: { miraDesktop: { ...desktop.miraDesktop, invoke } } });
  try {
    assert.match(view.container.textContent ?? "", /加载中…/);
    assert.doesNotMatch(view.container.textContent ?? "", /记忆插件不可用/);
  } finally {
    await view.cleanup();
    resetPluginEnabledStateForTests();
  }
});

it("shows a disconnected state without reading anything", async () => {
  resetPluginEnabledStateForTests();
  setPluginEnabledSnapshot([{ id: "default_memory", enabled: true, state: "ACTIVE" }]);
  const desktop = memoryDesktop(async () => ({ formData: { memory: { engine: "default" } } }));
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady={false} />, { windowGlobals: { miraDesktop: desktop.miraDesktop } });
  try {
    assert.match(view.container.textContent ?? "", /连接已断开/);
    assert.deepEqual(desktop.calls, []);
  } finally {
    await view.cleanup();
    resetPluginEnabledStateForTests();
  }
});
