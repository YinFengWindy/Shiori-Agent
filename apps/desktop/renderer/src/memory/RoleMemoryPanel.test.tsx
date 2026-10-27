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
type InvokeRequest = { method: string; payload: Record<string, unknown> };

/** A desktop bridge whose `memory.provider` answer can change between renders. */
function memoryDesktop(initial: string | null) {
  let pluginId = initial;
  const providerCalls: InvokeRequest[] = [];
  const listeners = new Set<(event: RuntimeEvent) => void>();
  const { invoke: rpcInvoke, calls } = createPluginRpcTestInvoke((name, params, id) => name === "roles.memory.documents"
    ? { role_id: params.role_id, documents: [] }
    : { role_id: params.role_id, status: "ready", items: [{ id: `${id}-1`, summary: `${id} memory` }], total: 1, page: 1, page_size: 20, filters: {} });
  const invoke = async (request: InvokeRequest) => {
    if (request.method === "memory.provider") {
      providerCalls.push(request);
      return { id: "1", type: "response" as const, method: request.method, error: null, payload: { plugin_id: pluginId } };
    }
    if (request.method === "plugins.list") return new Promise(() => {});
    return rpcInvoke(request as Parameters<typeof rpcInvoke>[0]);
  };
  return {
    calls,
    providerCalls,
    setPluginId: (id: string | null) => { pluginId = id; },
    failProvider: null as string | null,
    miraDesktop: {
      invoke,
      onEvent: (listener: (event: RuntimeEvent) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    },
  };
}

it("shows the plugin that provides memory, even when it is not default_memory", async () => {
  resetPluginEnabledStateForTests();
  setPluginEnabledSnapshot([{ id: "other_memory", enabled: true, state: "ACTIVE" }]);
  const desktop = memoryDesktop("other_memory");
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady />, { windowGlobals: { miraDesktop: desktop.miraDesktop } });
  try {
    assert.match(view.container.textContent ?? "", /other_memory memory/);
    assert.deepEqual(desktop.calls.map((call) => call.name).sort(), ["roles.memory.documents", "roles.memory.semantic.list"]);
    assert.ok(desktop.calls.every((call) => call.pluginId === "other_memory"));
    assert.equal(desktop.providerCalls.length, 1);
  } finally {
    await view.cleanup();
    resetPluginEnabledStateForTests();
  }
});

it("shows memory closed when default_memory is active but the socket is empty", async () => {
  resetPluginEnabledStateForTests();
  setPluginEnabledSnapshot([{ id: "default_memory", enabled: true, state: "ACTIVE" }]);
  const desktop = memoryDesktop(null);
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady />, { windowGlobals: { miraDesktop: desktop.miraDesktop } });
  try {
    assert.match(view.container.textContent ?? "", /记忆已关闭/);
    assert.deepEqual(desktop.calls, []);
    assert.equal(desktop.providerCalls.length, 1);
  } finally {
    await view.cleanup();
    resetPluginEnabledStateForTests();
  }
});

it("closes when a roster refresh reports that the provider is gone", async () => {
  resetPluginEnabledStateForTests();
  setPluginEnabledSnapshot([{ id: "other_memory", enabled: true, state: "ACTIVE" }]);
  const desktop = memoryDesktop("other_memory");
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady />, { windowGlobals: { miraDesktop: desktop.miraDesktop } });
  try {
    assert.match(view.container.textContent ?? "", /other_memory memory/);
    await act(async () => {
      desktop.setPluginId(null);
      setPluginEnabledSnapshot([{ id: "other_memory", enabled: false, state: "DISABLED" }]);
    });
    assert.match(view.container.textContent ?? "", /记忆已关闭/);
    assert.doesNotMatch(view.container.textContent ?? "", /other_memory memory/);
  } finally {
    await view.cleanup();
    resetPluginEnabledStateForTests();
  }
});

it("shows loading, not closed, while the plugin roster is still loading", async () => {
  resetPluginEnabledStateForTests();
  const desktop = memoryDesktop("default_memory");
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady />, { windowGlobals: { miraDesktop: desktop.miraDesktop } });
  try {
    assert.match(view.container.textContent ?? "", /加载中…/);
    assert.doesNotMatch(view.container.textContent ?? "", /记忆已关闭/);
    assert.equal(desktop.providerCalls.length, 0);
  } finally {
    await view.cleanup();
    resetPluginEnabledStateForTests();
  }
});

it("shows a disconnected state without reading anything", async () => {
  resetPluginEnabledStateForTests();
  setPluginEnabledSnapshot([{ id: "default_memory", enabled: true, state: "ACTIVE" }]);
  const desktop = memoryDesktop("default_memory");
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady={false} />, { windowGlobals: { miraDesktop: desktop.miraDesktop } });
  try {
    assert.match(view.container.textContent ?? "", /连接已断开/);
    assert.deepEqual(desktop.calls, []);
    assert.equal(desktop.providerCalls.length, 0);
  } finally {
    await view.cleanup();
    resetPluginEnabledStateForTests();
  }
});
