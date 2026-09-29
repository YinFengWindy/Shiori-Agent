import assert from "node:assert/strict";
import { test } from "node:test";
import * as PluginSdk from "@shiori/plugin-sdk";
import { mountTestComponent } from "../../renderer/src/shared/testing/domTestHarness";
import { initializeRuntimePluginPeers } from "../../renderer/src/plugins/runtimePluginPeers";
import { pluginUiImportMap } from "../../src/plugins/uiContract";
import { PluginUiResources } from "../../src/plugins/uiResources";

// Crosses the renderer peer installation, the import map and the main
// process's served peer wrapper (#503).
test("a precompiled plugin importing the SDK through the import map receives the host's instance", async () => {
  const view = await mountTestComponent(null);
  try {
    initializeRuntimePluginPeers();
    // Node has no import maps: resolve the bare specifier the way the browser
    // does, through the import map to the main process's served peer wrapper.
    const wrapperUrl = JSON.parse(pluginUiImportMap).imports["@shiori/plugin-sdk"];
    const wrapper = await (await new PluginUiResources("unused-workspace").load(wrapperUrl)).text();
    const precompiled = [
      'import { PluginBridgeError } from "@shiori/plugin-sdk";',
      'export default { pluginId: "external_sdk", PluginBridgeError };',
    ].join("\n").replace('"@shiori/plugin-sdk"', JSON.stringify(`data:text/javascript,${encodeURIComponent(wrapper)}`));
    // The wrapper reads the realm global the peers were installed on.
    Object.defineProperty(globalThis, "__shioriPluginPeers", { configurable: true, value: Reflect.get(window, "__shioriPluginPeers") });
    try {
      const plugin = (await import(/* @vite-ignore */ `data:text/javascript,${encodeURIComponent(precompiled)}`)).default;
      assert.equal(plugin.PluginBridgeError, PluginSdk.PluginBridgeError);
      assert.ok(new PluginSdk.PluginBridgeError("gone", "plugin_unavailable") instanceof plugin.PluginBridgeError);
    } finally { Reflect.deleteProperty(globalThis, "__shioriPluginPeers"); }
  } finally { await view.cleanup(); }
});
