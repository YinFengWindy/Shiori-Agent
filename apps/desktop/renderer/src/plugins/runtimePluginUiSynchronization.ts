import type { RuntimePluginUi } from "../../../src/plugins/uiContract";
import { loadRuntimePluginUi, type RuntimePluginUiHost } from "./runtimePluginUi";

/**
 * Identifies a package for the disposal/reload diff below — deliberately
 * excludes `activationToken` (#262): the backend mints a fresh one on every
 * generation, including one where this plugin's code did not change at all,
 * so including it here would tear down and reimport every plugin's UI on
 * every unrelated settings apply instead of only on a real package change.
 */
function packageIdentity(entry: RuntimePluginUi): string {
  return JSON.stringify({ pluginId: entry.pluginId, entry: entry.entry, css: entry.css, error: entry.error });
}

/** Serializes roster changes so a stale import cannot republish a disabled plugin. */
export function createRuntimePluginUiSynchronization(host: RuntimePluginUiHost) {
  const loaded = new Map<string, { identity: string; dispose: () => void }>();
  const failures = new Map<string, string>();
  let tail = Promise.resolve(new Map<string, string>());
  const synchronize = async (entries: RuntimePluginUi[]) => {
    const identities = new Map(entries.map((entry) => [entry.pluginId, packageIdentity(entry)]));
    for (const [id, value] of loaded) {
      if (identities.get(id) === value.identity) continue;
      value.dispose();
      loaded.delete(id);
      failures.delete(id);
    }
    for (const entry of entries) {
      if (loaded.has(entry.pluginId)) continue;
      const dispose = await loadRuntimePluginUi([entry], {
        ...host,
        failed: (failedEntry, error) => {
          failures.set(failedEntry.pluginId, error instanceof Error ? error.message : String(error));
          host.failed(failedEntry, error);
        },
      });
      loaded.set(entry.pluginId, { identity: packageIdentity(entry), dispose });
    }
    return new Map(failures);
  };
  return (entries: RuntimePluginUi[]) => {
    tail = tail.then(() => synchronize(entries), () => synchronize(entries));
    return tail;
  };
}
