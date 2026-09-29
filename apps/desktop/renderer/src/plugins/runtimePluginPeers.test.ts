import assert from "node:assert/strict";
import { test } from "node:test";
import * as React from "react";
import * as PluginSdk from "@shiori/plugin-sdk";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { initializeRuntimePluginPeers } from "./runtimePluginPeers";
import { pluginUiImportMap, pluginUiPeerExports } from "../../../src/plugins/uiContract";

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
