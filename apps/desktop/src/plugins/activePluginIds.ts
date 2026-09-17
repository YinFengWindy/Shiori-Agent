/** The subset of a plugin roster row this predicate needs. */
export type ActivePluginIdRow = { id: string; enabled: boolean; state: string };

/**
 * Admits a plugin id only when it is a unique, enabled, backend-`ACTIVE`
 * candidate.
 *
 * Shared by the renderer's nav/settings visibility predicate
 * (`apps/desktop/renderer/src/plugins/activePluginIds.ts`, which re-exports
 * this) and the main process's surface-teardown diff in `ipcRegistrations.ts`
 * (#262) — both need the identical "which plugin ids does the current roster
 * actually admit" answer, including the duplicate-id CONFLICT rule, and
 * previously only the renderer had it.
 */
export function activePluginIds(plugins: ActivePluginIdRow[]): Set<string> {
  const seen = new Set<string>();
  const active = new Set<string>();
  for (const plugin of plugins) {
    if (seen.has(plugin.id)) {
      active.delete(plugin.id);
      continue;
    }
    seen.add(plugin.id);
    if (plugin.enabled && plugin.state === "ACTIVE") active.add(plugin.id);
  }
  return active;
}
