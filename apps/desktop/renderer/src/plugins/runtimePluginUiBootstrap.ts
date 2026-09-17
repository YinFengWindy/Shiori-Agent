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

/** Installs shared React peers before evaluating any workspace plugin module. */
export function initializeRuntimePluginUi() {
  Object.defineProperty(globalThis, "__shioriPluginPeers", { value: Object.freeze({
    react: React, "react/jsx-runtime": ReactJsx, "react-dom": ReactDOM, "react-dom/client": ReactDOMClient,
  }), configurable: false, writable: false });
  const map = document.createElement("script");
  map.type = "importmap";
  map.textContent = pluginUiImportMap;
  document.head.append(map);
  registerPluginUiSynchronization(createRuntimePluginUiSynchronization({
    importModule: importRuntimePluginModule,
    loadCss: loadRuntimePluginCss,
    register: (module) => applyPluginUiModules({ runtime: { default: module } }),
    unregister: (pluginId) => {
      pluginUiRegistry.unregisterPlugin(pluginId);
      pluginRoleSettingsRegistry.unregister(pluginId);
      pluginChatImageActionsRegistry.unregister(pluginId);
    },
    failed: (pluginId, error) => {
      console.error(`[plugin-ui] ${pluginId}`, error);
      window.miraDesktop.reportRendererDiagnostic({ kind: "error", message: error instanceof Error ? error.message : String(error), details: { pluginId, event: "plugin-ui.load.failed", state: "FAILED", stage: "renderer" } });
    },
  }));
}
