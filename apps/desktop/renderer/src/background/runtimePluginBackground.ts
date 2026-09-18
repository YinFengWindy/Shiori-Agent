import { loadRuntimePluginModules } from "../plugins/runtimePluginModuleLoader";
import type { RuntimePluginUi } from "../../../src/plugins/uiContract";
import { isPluginBackgroundModule, type PluginBackgroundContribution } from "./pluginBackgroundContract";
import { pluginBackgroundRegistry, type PluginBackgroundRegistry } from "./pluginBackgroundRegistry";

/** Loader boundaries the plugin-host window's bootstrap supplies. */
export type RuntimePluginBackgroundHost = {
  importModule: (url: string) => Promise<{ default: unknown }>;
  loadCss: (url: string) => Promise<() => void>;
  succeeded?: (entry: RuntimePluginUi) => void;
  failed: (entry: RuntimePluginUi, error: unknown) => void;
};

/** Rejects a malformed contribution, or one whose identity does not match its admitted package. */
function assertRuntimePluginBackgroundModule(value: unknown, pluginId: string): asserts value is PluginBackgroundContribution {
  if (!isPluginBackgroundModule(value)) throw new Error("Invalid plugin background contribution");
  if (value.pluginId !== pluginId) throw new Error("Plugin background identity does not match its admitted package");
}

/**
 * Keep immutable module registrations so the background owner can dispose them.
 * Styles follow admission, while readiness is acknowledged for each new backend
 * activation token even when the browser reuses already evaluated module code.
 */
export function createRuntimePluginBackgroundLoader(
  host: RuntimePluginBackgroundHost,
  registry: PluginBackgroundRegistry = pluginBackgroundRegistry,
) {
  const loaded = new Map<string, { token: string | undefined; dispose: () => void }>();
  const failures = new Map<string, { token: string | undefined; error: unknown }>();
  return async (entries: RuntimePluginUi[]): Promise<string[]> => {
    const admitted = new Set(entries.map((entry) => entry.pluginId));
    for (const [id, state] of loaded) {
      if (!admitted.has(id)) { state.dispose(); loaded.delete(id); }
    }
    const handled: string[] = [];
    for (const entry of entries) {
      const previous = loaded.get(entry.pluginId);
      if (previous) {
        if (previous.token !== entry.activationToken) {
          previous.token = entry.activationToken;
          host.succeeded?.(entry);
        }
        continue;
      }
      const failure = failures.get(entry.pluginId);
      if (failure) {
        if (failure.token !== entry.activationToken) {
          failure.token = entry.activationToken;
          host.failed(entry, failure.error);
        }
        continue;
      }
      let succeeded = false;
      const dispose = await loadRuntimePluginModules([entry], {
        importModule: async (url) => {
          const cached = registry.get(entry.pluginId);
          return cached ? { default: { pluginId: cached.pluginId, setup: cached.setup } } : host.importModule(url);
        },
        loadCss: host.loadCss,
        validate: assertRuntimePluginBackgroundModule,
        register: (module) => {
          if (!registry.get(module.pluginId)) registry.register({ slot: "app.background", pluginId: module.pluginId, setup: module.setup });
        },
        // Registration remains until host exit so reconcile can still tear down
        // the old effect scope; this disposer only releases stylesheet nodes.
        unregister: () => undefined,
        succeeded: (entry) => { succeeded = true; host.succeeded?.(entry); },
        failed: (entry, error) => { failures.set(entry.pluginId, { token: entry.activationToken, error }); host.failed(entry, error); },
      });
      if (succeeded) loaded.set(entry.pluginId, { token: entry.activationToken, dispose });
      handled.push(entry.pluginId);
    }
    return handled;
  };
}
