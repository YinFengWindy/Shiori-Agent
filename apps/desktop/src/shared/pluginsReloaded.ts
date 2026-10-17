import type { BridgeEvent } from "@yinfengwindy/shiori-sdk/contract";

/**
 * Plugins the backend set up again, loaded or unloaded within the current
 * runtime generation (`plugins.reloaded`, after saving one plugin's config or
 * toggling it); empty for any other event. Shared by the main process
 * (native sessions) and the renderer (communication contexts, background
 * scopes).
 */
export function reloadedPluginIds(event: BridgeEvent): readonly string[] {
  const ids = event.method === "plugins.reloaded" ? event.payload.plugin_ids : undefined;
  return Array.isArray(ids) ? ids.filter((id): id is string => typeof id === "string") : [];
}
