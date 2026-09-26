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
  const listeners = new Set<(event: { method: string }) => void>();
  const view = await mountTestComponent(<RoleMemoryPanel roleId="mira" bridgeReady />, { windowGlobals: {
    miraDesktop: {
      readSettings: async () => ({ formData: { memory: { engine } } }),
      onEvent: (listener: (event: { method: string }) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    },
  } });
  try {
    assert.match(view.container.textContent ?? "", /Akasha mira/);
    assert.doesNotMatch(view.container.textContent ?? "", /Default/);
    await act(async () => { for (const listener of listeners) listener({ method: "runtime.applied" }); });
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
    await act(async () => { for (const listener of listeners) listener({ method: "runtime.applied" }); });
    assert.match(view.container.textContent ?? "", /Default mira/);
  } finally {
    await view.cleanup();
    pluginUiRegistry.unregisterPlugin("default_memory");
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
