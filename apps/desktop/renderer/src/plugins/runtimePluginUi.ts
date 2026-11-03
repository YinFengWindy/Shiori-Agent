import { validateRuntimePluginUi } from "./runtimePluginUiValidation";
import type { RuntimePluginFrontend } from "../../../src/plugins/uiContract";
import type { PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { loadRuntimePluginModules } from "./runtimePluginModuleLoader";

/** Loader boundaries keep module evaluation and CSS cleanup independently testable. */
export type RuntimePluginUiHost = {
  importModule: (url: string) => Promise<Record<string, unknown>>;
  loadCss: (url: string) => Promise<() => void>;
  register: (module: PluginUiModule) => void;
  unregister: (pluginId: string) => void;
  succeeded?: (entry: RuntimePluginFrontend) => void;
  failed: (entry: RuntimePluginFrontend, error: unknown) => void;
};

/**
 * Loads each admitted plugin independently and removes its partial UI on
 * failure. A thin wrapper over the shared `loadRuntimePluginModules` fixing
 * `validate` to the UI ABI — its observable behaviour (load order, cleanup
 * order, what gets reported) is unchanged from before that loader was
 * extracted for `background` and `surface` to reuse.
 */
export async function loadRuntimePluginUi(entries: RuntimePluginFrontend[], host: RuntimePluginUiHost) {
  return loadRuntimePluginModules(entries, "ui", { ...host, validate: assertRuntimePluginUiModule });
}

/** Rejects malformed contributions before any registry mutation. */
export function assertRuntimePluginUiModule(value: unknown, pluginId: string): asserts value is PluginUiModule {
  validateRuntimePluginUi(value, pluginId);
}
