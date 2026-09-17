import * as React from "react";
import * as ReactDOM from "react-dom";
import * as ReactDOMClient from "react-dom/client";
import * as ReactJsx from "react/jsx-runtime";
import { pluginUiImportMap } from "../../../src/plugins/uiContract";
import { applyPluginUiModules } from "./pluginUiModuleContract";
import { pluginUiRegistry } from "./pluginUiRegistry";
import { pluginChatImageActionsRegistry, pluginRoleSettingsRegistry } from "./pluginFeatureRegistry";
import { createRuntimePluginUiSynchronization } from "./runtimePluginUiSynchronization";
import { registerPluginUiSynchronization } from "./pluginEnabledStateStore";
import { importRuntimePluginModule, loadRuntimePluginCss } from "./runtimePluginDomLoader";
import { createPluginBridgeClient } from "./pluginBridgeClient";
import { reportRuntimePluginActivation, reportRuntimePluginRendererLoadFailure } from "./runtimePluginActivationReporting";

/** Installs shared React peers before evaluating any workspace plugin module. */
export function initializeRuntimePluginUi() {
  Object.defineProperty(globalThis, "__shioriPluginPeers", { value: Object.freeze({
    react: React, "react/jsx-runtime": ReactJsx, "react-dom": ReactDOM, "react-dom/client": ReactDOMClient,
  }), configurable: false, writable: false });
  const map = document.createElement("script");
  map.type = "importmap";
  map.textContent = pluginUiImportMap;
  document.head.append(map);
  const pluginBridge = createPluginBridgeClient();
  registerPluginUiSynchronization(createRuntimePluginUiSynchronization({
    importModule: importRuntimePluginModule,
    loadCss: loadRuntimePluginCss,
    register: (module) => applyPluginUiModules({ runtime: { default: module } }),
    unregister: (pluginId) => {
      pluginUiRegistry.unregisterPlugin(pluginId);
      pluginRoleSettingsRegistry.unregister(pluginId);
      pluginChatImageActionsRegistry.unregister(pluginId);
    },
    // Tells the backend this window's `ui` entry is ready, clearing it from
    // `pendingRendererKinds` (#262 AC1).
    succeeded: (entry) => reportRuntimePluginActivation(pluginBridge, entry, "ui", { ok: true }),
    // Rolls the whole plugin back on the backend so tools/RPC/background/
    // surface contributions do not outlive a UI that failed to load (#262 AC2).
    failed: (entry, error) => {
      console.error(`[plugin-ui] ${entry.pluginId}`, error);
      reportRuntimePluginRendererLoadFailure(pluginBridge, "plugin-ui.load.failed", entry, "ui", error);
    },
  }));
}
