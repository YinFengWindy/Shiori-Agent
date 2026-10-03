import assert from "node:assert/strict";
import { test } from "node:test";
import * as React from "react";
import * as PluginSdk from "@yinfengwindy/shiori-sdk";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
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
    assert.deepEqual(Object.keys(peers).sort(), [
      "@yinfengwindy/shiori-sdk", "react", "react-dom", "react-dom/client", "react/jsx-runtime",
    ]);
    assert.deepEqual(Object.keys(peers).sort(), Object.keys(pluginUiPeerExports).sort());
    assert.equal(peers["@yinfengwindy/shiori-sdk"], PluginSdk);
    assert.deepEqual([...pluginUiPeerExports["@yinfengwindy/shiori-sdk"]].sort(), Object.keys(PluginSdk).sort());
    const imports = JSON.parse(pluginUiImportMap).imports;
    assert.equal(imports["@yinfengwindy/shiori-sdk"], "shiori-plugin://host/@yinfengwindy/shiori-sdk.mjs");
    // The test entry is development-only and never a runtime peer.
    assert.equal(Object.keys(imports).some((name) => name.startsWith("@yinfengwindy/shiori-sdk/")), false);
    const testingExports = Object.keys(await import("@yinfengwindy/shiori-sdk/testing"));
    assert.ok(testingExports.includes("createFakeHostServices"));
    assert.deepEqual(testingExports.filter((name) => pluginUiPeerExports["@yinfengwindy/shiori-sdk"].includes(name)), []);
  } finally { await view.cleanup(); }
});
