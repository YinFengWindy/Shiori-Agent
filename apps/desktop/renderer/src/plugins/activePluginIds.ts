import type { PluginSummary } from "./pluginBridgeClient";

/** Admit renderer contributions only for unique, enabled, active backend IDs. */
export function activePluginIds(plugins: Pick<PluginSummary, "id" | "enabled" | "state">[]) {
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
