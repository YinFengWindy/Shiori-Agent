import type { PluginSummary } from "./pluginBridgeClient";

/** Only an installed, unique workspace candidate without queued changes is manageable. */
export function canManagePluginPackage(plugin: PluginSummary) {
  return plugin.source === "workspace" && plugin.packageInstalled !== false && plugin.state !== "CONFLICT"
    && !plugin.pendingOperation && !plugin.trustPendingRestart;
}

/** A missing/ineligible selection resolves to none; never silently targets another plugin. */
export function selectedPluginPackage(plugins: readonly PluginSummary[] | null, candidateId: string | null) {
  return plugins?.find((plugin) => plugin.candidateId === candidateId && canManagePluginPackage(plugin)) ?? null;
}
