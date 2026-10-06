import assert from "node:assert/strict";
import { test } from "node:test";
import { useEffect } from "react";
import type { PluginRoleUiProps } from "@yinfengwindy/shiori-sdk";
import { act } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { PluginRoleUiSlot } from "./PluginRoleUiSlot";
import { pluginRoleUiRegistry } from "./pluginFeatureRegistry";
import { readPluginRoleSettings, writePluginRoleSettings, buildPluginRoleDraftUpdates } from "./pluginRoleSettings";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "./pluginEnabledStateStore";

test("self-managed role UI gets identity and scoped calls but never enters the host role transaction", async () => {
  const disposed: string[] = []; const requests: string[] = [];
  function Editor({ roleId, client, onDirtyChange }: PluginRoleUiProps) {
    useEffect(() => () => { disposed.push(roleId ?? "new"); }, [roleId]);
    return <button disabled={!roleId} onClick={() => { onDirtyChange(true); void client.call("private.save", { role_id: roleId, private_marker: "only-plugin" }); }}>保存私有值</button>;
  }
  pluginRoleUiRegistry.register({ pluginId: "neutral", mode: "self-managed", Component: Editor });
  setPluginEnabledSnapshot([{ id: "neutral", enabled: true, state: "ACTIVE" }]);
  const view = await mountTestComponent(<PluginRoleUiSlot role={{ id: "one", name: "One", moodCatalog: [] }} disabled={false} />, { windowGlobals: { miraDesktop: {
    onEvent: () => () => {}, invoke: async ({ method }: { method: string }) => { requests.push(method); return { error: null, payload: { generation: "g" } }; },
  } } });
  try {
    await act(async () => view.container.querySelector("button")!.click());
    assert.ok(requests.includes("plugin.neutral.private.save"));
    assert.deepEqual(readPluginRoleSettings({}), {}); assert.deepEqual(writePluginRoleSettings({ keep: true }, { neutral: { private_marker: "only-plugin" } }), { keep: true });
    assert.deepEqual(buildPluginRoleDraftUpdates({ neutral: { private_marker: "only-plugin" } }), {});
    await view.render(<PluginRoleUiSlot role={{ id: "two", name: "Two", moodCatalog: [] }} disabled={false} />);
    assert.deepEqual(disposed, ["one"]);
    await view.render(<PluginRoleUiSlot role={null} disabled={false} />);
    assert.equal(view.container.querySelector("button")?.disabled, true);
  } finally { await view.cleanup(); pluginRoleUiRegistry.unregister("neutral"); resetPluginEnabledStateForTests(); }
});
