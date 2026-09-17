import { createPluginBridgeClient, type PluginBridgeClient, type PluginSummary } from "./pluginBridgeClient";
import { activePluginIds } from "./activePluginIds";
import { synchronizePluginSettingsAutoRegistration } from "./pluginSettingsAutoRegistration";
import type { RuntimePluginUi } from "../../../src/plugins/uiContract";

type Listener = () => void;

/** Answers whether one plugin id is currently enabled. */
export type PluginEnabledPredicate = (pluginId: string) => boolean;

// Module-level singleton: nav.page and settings.section visibility needs the
// same "is plugin X enabled" answer in several unrelated places (nav rail,
// settings sidebar, the settings page itself) that don't share a common
// mounted ancestor close enough for prop threading, and the plugin
// management list that flips the flag lives in yet another one. A small
// shared store (subscribe/notify, no external state library) is the
// narrowest thing that lets all of them agree on one answer immediately
// after a toggle, matching "停用后其 UI 入口...立即消失" (issue #174 AC 3).
let cache: Map<string, boolean> | null = null;
let inflight: Promise<void> | null = null;
const listeners = new Set<Listener>();
let synchronizeUi: ((entries: RuntimePluginUi[]) => Promise<Map<string, string>>) | undefined;
let refreshTail = Promise.resolve();

/** Installs the main-window runtime UI owner before the first roster refresh. */
export function registerPluginUiSynchronization(synchronize: (entries: RuntimePluginUi[]) => Promise<Map<string, string>>) {
  synchronizeUi = synchronize;
}

/** Refreshes renderer contributions before publishing one consistent enabled snapshot. */
export function refreshPluginEnabledState(client: Pick<PluginBridgeClient, "listPlugins"> = createPluginBridgeClient()) {
  const refresh = refreshTail.then(async () => {
    const plugins = await client.listPlugins();
    const failures = await synchronizeUi?.(plugins.flatMap((plugin) => plugin.rendererUi ? [plugin.rendererUi] : []));
    // Runs after synchronizeUi so every hand-written settings.section
    // (build-time glob + runtime plugins) is already registered before a
    // config-schema plugin without one is offered an auto-registered
    // subtab — see pluginSettingsAutoRegistration.ts (issue #230 AC 5/6).
    synchronizePluginSettingsAutoRegistration(plugins);
    const snapshot = plugins.map((plugin) => ({ ...plugin, rendererError: failures?.get(plugin.id) }));
    setPluginEnabledSnapshot(snapshot);
    return snapshot;
  });
  refreshTail = refresh.then(() => undefined, () => undefined);
  return refresh;
}

/**
 * Builds the predicate function exposed for the current cache state. A
 * fresh function is created (and its identity published via `predicate`)
 * every time the cache changes, never mutated in place, so a consumer that
 * uses this reference as a `useMemo`/`useCallback` dependency (as
 * `useSyncExternalStore` snapshots are meant to be used) recomputes instead
 * of reading a stale closure — see AGENTS.md on `useSyncExternalStore`.
 */
function createPredicate() {
  const snapshot = cache;
  // Before the roster has ever loaded — or for a plugin id the roster does
  // not (yet) know about — a plugin's nav/settings entry must not flash
  // visible and then disappear once the real state arrives. Treat "not yet
  // known" the same as "disabled" rather than fail-open to "enabled".
  return (pluginId: string) => snapshot?.get(pluginId) ?? false;
}

let predicate: PluginEnabledPredicate = createPredicate();

function notify() {
  predicate = createPredicate();
  for (const listener of listeners) listener();
}

/** Replaces the cached enabled flags wholesale (after a full `plugins.list` fetch). */
export function setPluginEnabledSnapshot(plugins: Pick<PluginSummary, "id" | "enabled" | "state">[]): void {
  cache = new Map([...activePluginIds(plugins)].map((id) => [id, true]));
  notify();
}

/** Synchronous read; a plugin not yet known to the cache is treated as disabled, not enabled. */
export function isPluginEnabled(pluginId: string): boolean {
  return predicate(pluginId);
}

/**
 * Returns the current predicate function; its identity changes whenever the
 * cache changes. Intended as a `useSyncExternalStore` snapshot getter (see
 * `usePluginEnabledState`), not for ad-hoc calls — use `isPluginEnabled` for
 * a one-off synchronous read outside React.
 */
export function getPluginEnabledPredicate(): PluginEnabledPredicate {
  return predicate;
}

/** Fetches the roster once (memoized); safe to call from multiple consumers. */
export async function ensurePluginEnabledStateLoaded(
  client: Pick<PluginBridgeClient, "listPlugins"> = createPluginBridgeClient(),
): Promise<void> {
  if (cache) return;
  if (!inflight) {
    inflight = refreshPluginEnabledState(client)
      .then(() => undefined)
      .finally(() => { inflight = null; });
  }
  await inflight;
}

export function subscribePluginEnabledState(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Test-only: clears memoized state so each test starts from a clean cache. */
export function resetPluginEnabledStateForTests(): void {
  cache = null;
  inflight = null;
  predicate = createPredicate();
  synchronizeUi = undefined;
  refreshTail = Promise.resolve();
}
