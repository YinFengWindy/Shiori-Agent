import type { PluginSummary } from "./pluginBridgeClient";

/** Only an installed, unique workspace candidate without queued changes is manageable. */
export function canManagePluginPackage(plugin: PluginSummary) {
  return plugin.source === "workspace" && plugin.packageInstalled !== false && plugin.state !== "CONFLICT"
    && !plugin.pendingOperation && !plugin.trustPendingRestart;
}

/** Resolve details from the current roster, including candidates that cannot be modified. */
export function pluginDetailsCandidate(plugins: readonly PluginSummary[] | null, candidateId: string | null) {
  return plugins?.find((plugin) => plugin.candidateId === candidateId) ?? null;
}
