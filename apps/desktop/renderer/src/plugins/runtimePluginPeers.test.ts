import assert from "node:assert/strict";
import { test } from "node:test";
import * as React from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { initializeRuntimePluginPeers } from "./runtimePluginPeers";
import { pluginUiImportMap } from "../../../src/plugins/uiContract";

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
