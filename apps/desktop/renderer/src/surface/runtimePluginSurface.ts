import { loadRuntimePluginModules } from "../plugins/runtimePluginModuleLoader";
import type { RuntimePluginUi } from "../../../src/plugins/uiContract";
import { isPluginSurfaceModule, type PluginSurfaceModule } from "./pluginSurfaceContract";
import { pluginSurfaceRegistry, type PluginSurfaceRegistry } from "./pluginSurfaceRegistry";

/** Loader boundaries a surface window's bootstrap supplies. */
export type RuntimePluginSurfaceHost = {
  importModule: (url: string) => Promise<{ default: unknown }>;
  loadCss: (url: string) => Promise<() => void>;
  failed: (pluginId: string, error: unknown) => void;
};

/** Rejects a malformed contribution, or one whose identity does not match its admitted package. */
function assertRuntimePluginSurfaceModule(value: unknown, pluginId: string): asserts value is PluginSurfaceModule {
  if (!isPluginSurfaceModule(value)) throw new Error("Invalid plugin surface contribution");
  if (value.pluginId !== pluginId) throw new Error("Plugin surface identity does not match its admitted package");
}

/**
 * Loads one admitted external plugin's `desktop.surface` entry into the exact
 * same `PluginSurfaceRegistry` the build-time glob (`pluginSurfaceModules.ts`)
 * populates, so `SurfaceRoot` mounts it — or shows its existing "this plugin
 * registered nothing" failure card — through the identical path a built-in
 * surface uses.
 *
 * A surface window is always scoped to exactly one plugin (the query string
 * fixes it, see `entry.ts`), so this loads at most one entry; a failure is
 * reported through `host.failed` and simply leaves the registry without an
 * entry for that plugin id, which `SurfaceRoot` already renders as a readable
 * failure card rather than a blank window.
 */
export async function loadRuntimePluginSurface(
  entry: RuntimePluginUi,
  host: RuntimePluginSurfaceHost,
  registry: PluginSurfaceRegistry = pluginSurfaceRegistry,
): Promise<void> {
  await loadRuntimePluginModules([entry], {
    importModule: host.importModule,
    loadCss: host.loadCss,
    validate: assertRuntimePluginSurfaceModule,
    register: (module) => registry.register({ slot: "desktop.surface", pluginId: module.pluginId, Component: module.surface.component }),
    unregister: (pluginId) => registry.unregister(pluginId),
    failed: host.failed,
  });
}
