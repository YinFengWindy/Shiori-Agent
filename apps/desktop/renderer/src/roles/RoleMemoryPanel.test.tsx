import assert from "node:assert/strict";
import { it } from "node:test";
import { act, useEffect } from "react";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "../plugins/pluginEnabledStateStore";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { RoleMemoryPanel } from "./RoleMemoryPanel";

it("shows only the configured enabled memory plugin and never falls back", async () => {
  resetPluginEnabledStateForTests();
  setPluginEnabledSnapshot([
    { id: "default_memory", enabled: true, state: "ACTIVE" },
    { id: "akasha", enabled: true, state: "ACTIVE" },
  ]);
  let akashaMounts = 0;
  function AkashaPanel({ roleId }: { roleId: string }) {
    useEffect(() => { akashaMounts += 1; }, []);
    return <p>Akasha {roleId}</p>;
  }
  pluginUiRegistry.registerRoleMemoryPanel({ slot: "role.memory", id: "default_memory", pluginId: "default_memory", Component: ({ roleId }) => <p>Default {roleId}</p> });
  pluginUiRegistry.registerRoleMemoryPanel({ slot: "role.memory", id: "akasha", pluginId: "akasha", Component: AkashaPanel });
  let engine = "akasha";
  const listeners = new Set<(event: { method: string; payload: { changed?: boolean } }) => void>();
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady />, { windowGlobals: {
    miraDesktop: {
      readSettings: async () => ({ formData: { memory: { engine } } }),
      onEvent: (listener: (event: { method: string; payload: { changed?: boolean } }) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    },
  } });
  try {
    assert.match(view.container.textContent ?? "", /Akasha mira/);
    assert.doesNotMatch(view.container.textContent ?? "", /Default/);
    await act(async () => { for (const listener of listeners) listener({ method: "runtime.applied", payload: { changed: false } }); });
    assert.match(view.container.textContent ?? "", /Akasha mira/);
    assert.doesNotMatch(view.container.textContent ?? "", /加载中/);
    assert.equal(akashaMounts, 1);
    await act(async () => setPluginEnabledSnapshot([
      { id: "default_memory", enabled: true, state: "ACTIVE" },
      { id: "akasha", enabled: false, state: "DISABLED" },
    ]));
    assert.match(view.container.textContent ?? "", /记忆插件不可用/);
    assert.doesNotMatch(view.container.textContent ?? "", /Default/);

    engine = "default";
    await act(async () => { for (const listener of listeners) listener({ method: "runtime.applied", payload: { changed: true } }); });
    assert.match(view.container.textContent ?? "", /Default mira/);
  } finally {
    await view.cleanup();
    pluginUiRegistry.unregisterPlugin("default_memory");
    pluginUiRegistry.unregisterPlugin("akasha");
    resetPluginEnabledStateForTests();
  }
});

it("hides old engine content while a changed runtime read is pending", async () => {
  resetPluginEnabledStateForTests();
  setPluginEnabledSnapshot([
    { id: "default_memory", enabled: true, state: "ACTIVE" },
    { id: "akasha", enabled: true, state: "ACTIVE" },
  ]);
  pluginUiRegistry.registerRoleMemoryPanel({ slot: "role.memory", id: "default_memory", pluginId: "default_memory", Component: () => <p>Default memory</p> });
  pluginUiRegistry.registerRoleMemoryPanel({ slot: "role.memory", id: "akasha", pluginId: "akasha", Component: () => <p>Akasha private memory</p> });
  let reads = 0;
  let resolveNext: ((value: unknown) => void) | undefined;
  const listeners = new Set<(event: { method: string; payload: { changed?: boolean } }) => void>();
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady />, { windowGlobals: {
    miraDesktop: {
      readSettings: () => ++reads === 1
        ? Promise.resolve({ formData: { memory: { engine: "akasha" } } })
        : new Promise((resolve) => { resolveNext = resolve; }),
      onEvent: (listener: (event: { method: string; payload: { changed?: boolean } }) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    },
  } });
  try {
    assert.match(view.container.textContent ?? "", /Akasha private memory/);
    await act(async () => { for (const listener of listeners) listener({ method: "runtime.applied", payload: { changed: true } }); });
    assert.match(view.container.textContent ?? "", /加载中/);
    assert.doesNotMatch(view.container.textContent ?? "", /Akasha private memory/);
    await act(async () => resolveNext?.({ formData: { memory: { engine: "default" } } }));
    assert.match(view.container.textContent ?? "", /Default memory/);
    assert.doesNotMatch(view.container.textContent ?? "", /Akasha private memory/);
  } finally {
    await view.cleanup();
    pluginUiRegistry.unregisterPlugin("default_memory");
    pluginUiRegistry.unregisterPlugin("akasha");
    resetPluginEnabledStateForTests();
  }
});

it("shows a settings error after an engine-switch read fails, without stale data", async () => {
  resetPluginEnabledStateForTests();
  setPluginEnabledSnapshot([{ id: "akasha", enabled: true, state: "ACTIVE" }]);
  pluginUiRegistry.registerRoleMemoryPanel({ slot: "role.memory", id: "akasha", pluginId: "akasha", Component: () => <p>Akasha private memory</p> });
  let reads = 0;
  const listeners = new Set<(event: { method: string; payload: { changed?: boolean } }) => void>();
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady />, { windowGlobals: {
    miraDesktop: {
      readSettings: () => ++reads === 1
        ? Promise.resolve({ formData: { memory: { engine: "akasha" } } })
        : Promise.reject(new Error("settings stalled")),
      onEvent: (listener: (event: { method: string; payload: { changed?: boolean } }) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    },
  } });
  try {
    assert.match(view.container.textContent ?? "", /Akasha private memory/);
    await act(async () => { for (const listener of listeners) listener({ method: "runtime.applied", payload: { changed: true } }); });
    assert.match(view.container.textContent ?? "", /记忆设置读取失败：settings stalled/);
    assert.ok(view.container.querySelector('[role="alert"]'));
    assert.doesNotMatch(view.container.textContent ?? "", /Akasha private memory/);
  } finally {
    await view.cleanup();
    pluginUiRegistry.unregisterPlugin("akasha");
    resetPluginEnabledStateForTests();
  }
});

it("uses the shared page error for a failed settings read", async () => {
  resetPluginEnabledStateForTests();
  setPluginEnabledSnapshot([]);
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady />, { windowGlobals: {
    miraDesktop: {
      readSettings: async () => { throw new Error("settings unavailable"); },
      onEvent: () => () => {},
    },
  } });
  try {
    assert.match(view.container.textContent ?? "", /记忆设置读取失败：settings unavailable/);
    assert.ok(view.container.querySelector('[role="alert"]'));
  } finally {
    await view.cleanup();
    resetPluginEnabledStateForTests();
  }
});
