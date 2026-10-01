import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement, type ComponentType } from "react";
import * as PluginSdk from "@shiori/sdk";
import { mountTestComponent } from "@shiori/sdk/testing";
import { pluginHostServicesFor } from "../../renderer/src/plugins/pluginHostServices";
import { applyPluginUiModules } from "../../renderer/src/plugins/pluginUiModuleContract";
import { PluginUiRegistry } from "../../renderer/src/plugins/pluginUiRegistry";
import { initializeRuntimePluginPeers } from "../../renderer/src/plugins/runtimePluginPeers";
import { pluginUiImportMap } from "../../src/plugins/uiContract";
import { PluginUiResources } from "../../src/plugins/uiResources";

/**
 * Loads `source` as a precompiled plugin module whose `@shiori/sdk`
 * import resolves the way the browser's does: through the import map to the
 * main process's served peer wrapper (Node has no import maps). Call inside a
 * mounted window with the peers installed.
 */
async function importPrecompiledPlugin(source: string) {
  const wrapperUrl = JSON.parse(pluginUiImportMap).imports["@shiori/sdk"];
  const wrapper = await (await new PluginUiResources("unused-workspace").load(wrapperUrl)).text();
  const precompiled = source.replace('"@shiori/sdk"', JSON.stringify(`data:text/javascript,${encodeURIComponent(wrapper)}`));
  // The wrapper reads the realm global the peers were installed on.
  Object.defineProperty(globalThis, "__shioriPluginPeers", { configurable: true, value: Reflect.get(window, "__shioriPluginPeers") });
  try {
    return (await import(/* @vite-ignore */ `data:text/javascript,${encodeURIComponent(precompiled)}`)).default;
  } finally { Reflect.deleteProperty(globalThis, "__shioriPluginPeers"); }
}

// Crosses the renderer peer installation, the import map and the main
// process's served peer wrapper (#503).
test("a precompiled plugin importing the SDK through the import map receives the host's instance", async () => {
  const view = await mountTestComponent(null);
  try {
    initializeRuntimePluginPeers();
    const plugin = await importPrecompiledPlugin([
      'import { PluginBridgeError } from "@shiori/sdk";',
      'export default { pluginId: "external_sdk", PluginBridgeError };',
    ].join("\n"));
    assert.equal(plugin.PluginBridgeError, PluginSdk.PluginBridgeError);
    assert.ok(new PluginSdk.PluginBridgeError("gone", "plugin_unavailable") instanceof plugin.PluginBridgeError);
  } finally { await view.cleanup(); }
});

// Runtime API 2.10.0 (#505): the host mounts every contribution under the
// SDK's Provider, and a deep component of an external plugin reads that
// context through its own peer-resolved `usePluginHostServices`.
test("a precompiled plugin's usePluginHostServices reads the services the host mounted its page with", async () => {
  const view = await mountTestComponent(null, { windowGlobals: { miraDesktop: { onEvent: () => () => undefined } } });
  try {
    initializeRuntimePluginPeers();
    const plugin = await importPrecompiledPlugin([
      'import { usePluginHostServices } from "@shiori/sdk";',
      "const seen = [];",
      "function Page() { seen.push(usePluginHostServices()); return null; }",
      'export default { pluginId: "external_sdk", navPage: { label: "External", component: Page }, seen };',
    ].join("\n"));
    const registry = new PluginUiRegistry();
    applyPluginUiModules({ "external_sdk/ui.mjs": { default: plugin } }, registry);
    const NavPage = registry.getNavPage("external_sdk")?.Component as ComponentType<{ pageId: string }>;
    await view.render(createElement(NavPage, { pageId: "external_sdk" }));
    assert.ok(plugin.seen.length > 0);
    for (const services of plugin.seen) assert.equal(services, pluginHostServicesFor("external_sdk"));
  } finally { await view.cleanup(); }
});
