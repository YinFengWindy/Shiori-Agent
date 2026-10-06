import assert from "node:assert/strict";
import { test } from "node:test";
import { useEffect } from "react";
import { usePluginHostServices, type NativeFilePickerOptions, type PluginHostServices, type PluginRoleUiProps } from "@yinfengwindy/shiori-sdk";
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

test("private role UI receives stable scoped host services for native file selection", async () => {
  const services: PluginHostServices[] = [];
  const picks: NativeFilePickerOptions[] = [];
  const requests: string[] = [];
  function Editor() {
    const host = usePluginHostServices();
    services.push(host);
    return <button onClick={() => { void host.pickFiles({ namespace: "neutral-picker", maxFileBytes: 1024, filters: [{ name: "Audio", extensions: ["wav"] }] }); }}>选择文件</button>;
  }
  pluginRoleUiRegistry.register({ pluginId: "neutral-picker", mode: "self-managed", Component: Editor });
  setPluginEnabledSnapshot([{ id: "neutral-picker", enabled: true, state: "ACTIVE" }]);
  const view = await mountTestComponent(<PluginRoleUiSlot role={{ id: "one", name: "One", moodCatalog: [] }} disabled={false} />, { windowGlobals: { miraDesktop: {
    onEvent: () => () => {},
    invoke: async ({ method }: { method: string }) => { requests.push(method); return { error: null, payload: { generation: "g" } }; },
    pickFiles: async (options: NativeFilePickerOptions) => { picks.push(options); return ["/private/selected.wav"]; },
  } } });
  try {
    await act(async () => view.container.querySelector("button")!.click());
    assert.equal(picks.length, 1);
    assert.equal(picks[0].namespace, "neutral-picker");
    await view.render(<PluginRoleUiSlot role={{ id: "two", name: "Two", moodCatalog: [] }} disabled={false} />);
    assert.ok(services.length >= 2);
    assert.ok(services.every((host) => host === services[0]));
    assert.equal(requests.includes("roles.update"), false);
  } finally { await view.cleanup(); pluginRoleUiRegistry.unregister("neutral-picker"); resetPluginEnabledStateForTests(); }
});
