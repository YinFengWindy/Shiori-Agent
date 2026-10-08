import assert from "node:assert/strict";
import { test } from "node:test";
import { act, useEffect } from "react";
import { usePluginHostServices, type PluginRoleSettingsProps } from "@yinfengwindy/shiori-sdk";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { PluginRoleSettingsSlot } from "./PluginRoleSettingsSlot";
import { pluginRoleSettingsRegistry } from "./pluginFeatureRegistry";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "./pluginEnabledStateStore";

test("role settings get the role id, a scoped client and host services, and remount per role", async () => {
  const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
  const disposed: string[] = [];
  function Card({ roleId, client }: PluginRoleSettingsProps) {
    const host = usePluginHostServices();
    useEffect(() => () => { disposed.push(roleId ?? "new"); }, [roleId]);
    return <button data-has-host={String(typeof host.pickFiles === "function")}
      onClick={() => { void client.call("live.save", { role_id: roleId }); }}>保存</button>;
  }
  pluginRoleSettingsRegistry.register({ pluginId: "neutral-card", storage: "plugin", read: () => ({}), Component: Card });
  setPluginEnabledSnapshot([{ id: "neutral-card", enabled: true, state: "ACTIVE" }]);
  const slot = (roleId: string) => <PluginRoleSettingsSlot roleId={roleId} drafts={{}} onChange={() => undefined} />;
  const view = await mountTestComponent(slot("one"), { windowGlobals: { miraDesktop: {
    onEvent: () => () => {},
    invoke: async (request: { method: string; payload: Record<string, unknown> }) => { requests.push(request); return { error: null, payload: { generation: "g" } }; },
  } } });
  try {
    const button = view.container.querySelector("button")!;
    assert.equal(button.dataset.hasHost, "true");
    await act(async () => button.click());
    const save = requests.find((request) => request.method === "plugin.neutral-card.live.save");
    assert.equal(save?.payload.role_id, "one");
    assert.equal(requests.some((request) => request.method === "roles.update"), false);
    await view.render(slot("two"));
    assert.deepEqual(disposed, ["one"]);
  } finally { await view.cleanup(); pluginRoleSettingsRegistry.unregister("neutral-card"); resetPluginEnabledStateForTests(); }
});
