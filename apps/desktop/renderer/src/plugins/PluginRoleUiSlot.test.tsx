import assert from "node:assert/strict";
import { test } from "node:test";
import { useEffect } from "react";
import type { PluginRoleUiProps } from "@yinfengwindy/shiori-sdk";
import { act } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { PluginRoleUiSlot } from "./PluginRoleUiSlot";
import { pluginRoleUiRegistry } from "./pluginFeatureRegistry";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "./pluginEnabledStateStore";

test("self-managed role UI gets identity and scoped calls but never enters the host role transaction", async () => {
  const disposed: string[] = [];
  const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
  function Editor({ roleId, client, onDirtyChange }: PluginRoleUiProps) {
    useEffect(() => () => { disposed.push(roleId ?? "new"); }, [roleId]);
    return <button disabled={!roleId} onClick={() => { onDirtyChange(true); void client.call("private.save", { role_id: roleId, private_marker: "only-plugin" }); }}>保存私有值</button>;
  }
  pluginRoleUiRegistry.register({ pluginId: "neutral", mode: "self-managed", Component: Editor });
  setPluginEnabledSnapshot([{ id: "neutral", enabled: true, state: "ACTIVE" }]);
  const view = await mountTestComponent(<PluginRoleUiSlot role={{ id: "one", name: "One", moodCatalog: [] }} disabled={false} />, { windowGlobals: { miraDesktop: {
    onEvent: () => () => {}, invoke: async (request: { method: string; payload: Record<string, unknown> }) => { requests.push(request); return { error: null, payload: { generation: "g" } }; },
  } } });
  try {
    await act(async () => view.container.querySelector("button")!.click());
    const save = requests.find((request) => request.method === "plugin.neutral.private.save");
    assert.equal(save?.payload.role_id, "one");
    assert.equal(save?.payload.private_marker, "only-plugin");
    assert.equal(requests.some((request) => request.method === "roles.update"), false);
    await view.render(<PluginRoleUiSlot role={{ id: "two", name: "Two", moodCatalog: [] }} disabled={false} />);
    assert.deepEqual(disposed, ["one"]);
    await view.render(<PluginRoleUiSlot role={null} disabled={false} />);
    assert.equal(view.container.querySelector("button")?.disabled, true);
  } finally { await view.cleanup(); pluginRoleUiRegistry.unregister("neutral"); resetPluginEnabledStateForTests(); }
});
