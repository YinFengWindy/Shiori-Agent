import assert from "node:assert/strict";
import { test } from "node:test";
import { act, useEffect, useState } from "react";
import { usePluginHostServices, type BridgeEvent, type PluginRoleSettingsProps } from "@yinfengwindy/shiori-sdk";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { PluginRoleSettingsSlot } from "./PluginRoleSettingsSlot";
import { pluginRoleSettingsRegistry } from "./pluginFeatureRegistry";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "./pluginEnabledStateStore";

test("role settings get the role id, its mood catalog, a scoped client and host services, and remount per role", async () => {
  const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
  const disposed: string[] = [];
  function Card({ roleId, client, moodCatalog }: PluginRoleSettingsProps) {
    const host = usePluginHostServices();
    useEffect(() => () => { disposed.push(roleId ?? "new"); }, [roleId]);
    return <button data-has-host={String(typeof host.pickFiles === "function")} data-moods={moodCatalog.join(",")}
      onClick={() => { void client.call("live.save", { role_id: roleId }); }}>保存</button>;
  }
  pluginRoleSettingsRegistry.register({ pluginId: "neutral-card", storage: "plugin", read: () => ({}), Component: Card });
  setPluginEnabledSnapshot([{ id: "neutral-card", enabled: true, state: "ACTIVE" }]);
  const slot = (roleId: string) => <PluginRoleSettingsSlot roleId={roleId} moodCatalog={["平静", "开心"]} drafts={{}} onChange={() => undefined} />;
  const view = await mountTestComponent(slot("one"), { windowGlobals: { miraDesktop: {
    onEvent: () => () => {},
    invoke: async (request: { method: string; payload: Record<string, unknown> }) => { requests.push(request); return { error: null, payload: { generation: "g" } }; },
  } } });
  try {
    const button = view.container.querySelector("button")!;
    assert.equal(button.dataset.hasHost, "true");
    assert.equal(button.dataset.moods, "平静,开心");
    await act(async () => button.click());
    const save = requests.find((request) => request.method === "neutral-card.live.save");
    assert.equal(save?.payload.role_id, "one");
    assert.equal(requests.some((request) => request.method === "roles.update"), false);
    await view.render(slot("two"));
    assert.deepEqual(disposed, ["one"]);
  } finally { await view.cleanup(); pluginRoleSettingsRegistry.unregister("neutral-card"); resetPluginEnabledStateForTests(); }
});

test("same-code reload remounts only its role card while retaining the host's draft", async () => {
  const listeners = new Set<(event: BridgeEvent) => void>();
  function Card({ values, onChange }: PluginRoleSettingsProps) {
    const [privateValue, setPrivateValue] = useState(0);
    return <button onClick={() => { setPrivateValue((value) => value + 1); onChange({ note: "edited draft" }); }}>
      {String(values.note)}:{privateValue}
    </button>;
  }
  function Editor() {
    const [drafts, setDrafts] = useState({ sample: { note: "initial" }, sibling: { note: "other" } });
    return <PluginRoleSettingsSlot roleId="mira" moodCatalog={[]} drafts={drafts} onChange={(next) => setDrafts({ sample: { note: String(next.sample.note) }, sibling: { note: String(next.sibling.note) } })} />;
  }
  for (const pluginId of ["sample", "sibling"]) pluginRoleSettingsRegistry.register({ pluginId, storage: "plugin", read: () => ({}), Component: Card });
  setPluginEnabledSnapshot(["sample", "sibling"].map((id) => ({ id, enabled: true, state: "ACTIVE" })));
  const view = await mountTestComponent(<Editor />, { windowGlobals: { miraDesktop: {
    onEvent: (listener: (event: BridgeEvent) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
  } } });
  const emit = async (method: string, payload: Record<string, unknown>) => act(async () => {
    for (const listener of [...listeners]) listener({ id: "event", type: "event", method, payload });
  });
  try {
    for (const button of Array.from(view.container.querySelectorAll("button"))) await act(async () => button.click());
    assert.deepEqual(Array.from(view.container.querySelectorAll("button"), (button) => button.textContent), ["edited draft:1", "edited draft:1"]);
    await emit("runtime.applied", { changed: false });
    await emit("plugins.reloaded", { plugin_ids: ["unrelated"] });
    assert.deepEqual(Array.from(view.container.querySelectorAll("button"), (button) => button.textContent), ["edited draft:1", "edited draft:1"]);
    await emit("plugins.reloaded", { plugin_ids: ["sample"] });
    assert.deepEqual(Array.from(view.container.querySelectorAll("button"), (button) => button.textContent), ["edited draft:0", "edited draft:1"]);
    assert.equal(listeners.size, 2);
  } finally {
    await view.cleanup();
    for (const id of ["sample", "sibling"]) pluginRoleSettingsRegistry.unregister(id);
    resetPluginEnabledStateForTests();
  }
  assert.equal(listeners.size, 0);
});
