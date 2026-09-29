import assert from "node:assert/strict";
import { test } from "node:test";
import * as React from "react";
import * as PluginSdk from "@shiori/plugin-sdk";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { initializeRuntimePluginPeers } from "./runtimePluginPeers";
import { pluginUiImportMap, pluginUiPeerExports } from "../../../src/plugins/uiContract";
import { PluginUiResources } from "../../../src/plugins/uiResources";

test("each renderer document resolves peers to its host React without duplicate import maps", async () => {
  for (const kind of ["ui", "background", "surface"]) {
    const view = await mountTestComponent(null);
    try {
      initializeRuntimePluginPeers();
      initializeRuntimePluginPeers();
      const maps = document.head.querySelectorAll('script[type="importmap"]');
      assert.equal(maps.length, 1, kind);
      assert.equal(maps[0].textContent, pluginUiImportMap);
      const peers = Reflect.get(window, "__shioriPluginPeers");
      assert.equal(peers.react.useState, React.useState);
      assert.equal(peers.react.createElement, React.createElement);
      assert.ok(Object.isFrozen(peers));
      assert.equal(Reflect.set(window, "__shioriPluginPeers", {}), false);
    } finally { await view.cleanup(); }
  }
});

test("every peer in the ABI is installed, and the SDK export list matches the host SDK instance", async () => {
  const view = await mountTestComponent(null);
  try {
    initializeRuntimePluginPeers();
    const peers = Reflect.get(window, "__shioriPluginPeers");
    assert.deepEqual(Object.keys(peers).sort(), Object.keys(pluginUiPeerExports).sort());
    assert.equal(peers["@shiori/plugin-sdk"], PluginSdk);
    assert.deepEqual([...pluginUiPeerExports["@shiori/plugin-sdk"]].sort(), Object.keys(PluginSdk).sort());
    const imports = JSON.parse(pluginUiImportMap).imports;
    assert.equal(imports["@shiori/plugin-sdk"], "shiori-plugin://host/@shiori/plugin-sdk.mjs");
    // The test entry is development-only and never a runtime peer.
    assert.equal(Object.keys(imports).some((name) => name.startsWith("@shiori/plugin-sdk/")), false);
  } finally { await view.cleanup(); }
});

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
