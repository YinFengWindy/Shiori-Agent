import type { RuntimePluginUi } from "../../../src/plugins/uiContract";
import { loadRuntimePluginUi, type RuntimePluginUiHost } from "./runtimePluginUi";

/** Serializes roster changes so a stale import cannot republish a disabled plugin. */
export function createRuntimePluginUiSynchronization(host: RuntimePluginUiHost) {
  const loaded = new Map<string, { identity: string; dispose: () => void }>();
  const failures = new Map<string, string>();
  let tail = Promise.resolve(new Map<string, string>());
  const synchronize = async (entries: RuntimePluginUi[]) => {
    const identities = new Map(entries.map((entry) => [entry.pluginId, JSON.stringify(entry)]));
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
        failed: (id, error) => {
          failures.set(id, error instanceof Error ? error.message : String(error));
          host.failed(id, error);
        },
      });
      loaded.set(entry.pluginId, { identity: JSON.stringify(entry), dispose });
    }
    return new Map(failures);
  };
  return (entries: RuntimePluginUi[]) => {
    tail = tail.then(() => synchronize(entries), () => synchronize(entries));
    return tail;
  };
}
