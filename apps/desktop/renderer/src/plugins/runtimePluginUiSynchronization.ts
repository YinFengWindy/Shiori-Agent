import type { RuntimePluginUi } from "../../../src/plugins/uiContract";
import { loadRuntimePluginUi, type RuntimePluginUiHost } from "./runtimePluginUi";

/**
 * Identifies a package for the disposal/reload diff below — everything in
 * the admitted entry except `activationToken` (#262), which the backend
 * mints fresh on every generation including ones where this plugin's code
 * did not change at all. Including it would tear down and reimport every
 * plugin's UI on every unrelated settings apply instead of only on a real
 * package change.
 *
 * Written as an exclusion rather than a list of the fields to compare, so a
 * field added to `RuntimePluginUi` later participates in the diff by
 * default. The safe failure for an unknown new field is an extra reload; a
 * field that silently stops being compared would leave stale code loaded
 * with nothing to signal it.
 */
function packageIdentity(entry: RuntimePluginUi): string {
  // `JSON.stringify` omits undefined-valued keys, so overriding is enough to
  // drop the token while every other field — present and future — is carried
  // through by the spread.
  return JSON.stringify({ ...entry, activationToken: undefined });
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
