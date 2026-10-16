import type { BridgeEvent } from "@yinfengwindy/shiori-sdk";

/** No-op configuration writes leave existing plugin contexts and requests alive. */
export function pluginRuntimeChanged(event: BridgeEvent) {
  return (event.method === "runtime.applied" && event.payload.changed !== false)
    || event.method === "bridge.exit" || event.method === "bridge.ready";
}

/**
 * Plugins the backend set up again within the current runtime generation
 * (`plugins.reloaded`, e.g. after saving one plugin's config); empty for any
 * other event. Only these plugins' renderer contexts are replaced.
 */
export function reloadedPluginIds(event: BridgeEvent): readonly string[] {
  const ids = event.method === "plugins.reloaded" ? event.payload.plugin_ids : undefined;
  return Array.isArray(ids) ? ids.filter((id): id is string => typeof id === "string") : [];
}

/** Whether `pluginId`'s communication context belongs to a replaced runtime or instance. */
export function pluginContextReplaced(event: BridgeEvent, pluginId: string) {
  return pluginRuntimeChanged(event) || reloadedPluginIds(event).includes(pluginId);
}

/** Roster changes refresh availability without replacing a runtime generation. */
export function pluginRosterChanged(event: BridgeEvent) {
  return event.method === "plugins.changed" || event.method === "plugins.reloaded" || pluginRuntimeChanged(event);
}
