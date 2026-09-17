import { loadRuntimePluginModules } from "../plugins/runtimePluginModuleLoader";
import type { RuntimePluginUi } from "../../../src/plugins/uiContract";
import { isPluginBackgroundModule, type PluginBackgroundContribution } from "./pluginBackgroundContract";
import { pluginBackgroundRegistry, type PluginBackgroundRegistry } from "./pluginBackgroundRegistry";

/** Loader boundaries the plugin-host window's bootstrap supplies. */
export type RuntimePluginBackgroundHost = {
  importModule: (url: string) => Promise<{ default: unknown }>;
  loadCss: (url: string) => Promise<() => void>;
  failed: (pluginId: string, error: unknown) => void;
};

/** Rejects a malformed contribution, or one whose identity does not match its admitted package. */
function assertRuntimePluginBackgroundModule(value: unknown, pluginId: string): asserts value is PluginBackgroundContribution {
  if (!isPluginBackgroundModule(value)) throw new Error("Invalid plugin background contribution");
  if (value.pluginId !== pluginId) throw new Error("Plugin background identity does not match its admitted package");
}

/**
 * Loads and registers every admitted external-plugin `app.background` entry
 * this window has not already handled, into the exact same
 * `PluginBackgroundRegistry` the build-time glob (`pluginBackgroundModules.ts`)
 * populates — so `PluginBackgroundHost` governs its run/stop lifecycle
 * exactly like a built-in module, through the same `BackgroundEffectScope`.
 *
 * Deliberately idempotent rather than diff-based like
 * `runtimePluginUiSynchronization`: `PluginUiResources.admit` refuses a
 * changed package identity until restart, so an admitted entry's code can
 * never change mid-session, and once it is registered (or its failure
 * reported) there is nothing left to reconsider. This also sidesteps a real
 * hazard a diff-based re-synchronization would introduce here: unregistering
 * a plugin the moment it disappears from the admitted roster (e.g. because it
 * was just disabled) would remove it from `pluginBackgroundRegistry` before
 * `PluginBackgroundHost.reconcile()` gets a chance to see it and tear down its
 * still-running `BackgroundEffectScope` — orphaning that scope forever, since
 * nothing would be left with a reference to it. Leaving a disabled plugin's
 * entry registered is exactly what already happens for a disabled built-in
 * plugin, and `PluginBackgroundHost` already handles that correctly.
 *
 * Returns the plugin ids this call newly registered or reported failed, for
 * tests; production callers do not need it.
 */
export function createRuntimePluginBackgroundLoader(
  host: RuntimePluginBackgroundHost,
  registry: PluginBackgroundRegistry = pluginBackgroundRegistry,
) {
  const reported = new Set<string>();
  return async (entries: RuntimePluginUi[]): Promise<string[]> => {
    const pending = entries.filter((entry) => !registry.get(entry.pluginId) && !reported.has(entry.pluginId));
    if (pending.length === 0) return [];
    await loadRuntimePluginModules(pending, {
      importModule: host.importModule,
      loadCss: host.loadCss,
      validate: assertRuntimePluginBackgroundModule,
      register: (module) => registry.register({ slot: "app.background", pluginId: module.pluginId, setup: module.setup }),
      // A background module, once registered, is never unregistered here — see above.
      unregister: () => undefined,
      failed: (pluginId, error) => { reported.add(pluginId); host.failed(pluginId, error); },
    });
    return pending.map((entry) => entry.pluginId);
  };
}
