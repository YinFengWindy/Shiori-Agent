import { applyPluginUiModules } from "./pluginUiModuleContract";
import { pluginUiRegistry } from "./pluginUiRegistry";
import { pluginChatImageActionsRegistry, pluginRoleSettingsRegistry } from "./pluginFeatureRegistry";
import { createRuntimePluginUiSynchronization } from "./runtimePluginUiSynchronization";
import { registerPluginUiSynchronization } from "./pluginEnabledStateStore";
import { importRuntimePluginModule, loadRuntimePluginCss } from "./runtimePluginDomLoader";
import { createPluginBridgeClient } from "./pluginBridgeClient";
import { reportRuntimePluginActivation, reportRuntimePluginRendererLoadFailure } from "./runtimePluginActivationReporting";

/** Coordinates runtime UI contributions with the current plugin roster. */
export function initializeRuntimePluginUi() {
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
