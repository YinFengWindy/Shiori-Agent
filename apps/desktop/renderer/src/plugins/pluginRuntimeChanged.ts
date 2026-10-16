import type { BridgeEvent } from "@yinfengwindy/shiori-sdk";
import { reloadedPluginIds } from "../../../src/shared/pluginsReloaded";

/** No-op configuration writes leave existing plugin contexts and requests alive. */
export function pluginRuntimeChanged(event: BridgeEvent) {
  return (event.method === "runtime.applied" && event.payload.changed !== false)
    || event.method === "bridge.exit" || event.method === "bridge.ready";
}

/** Whether `pluginId`'s communication context belongs to a replaced runtime or instance. */
export function pluginContextReplaced(event: BridgeEvent, pluginId: string) {
  return pluginRuntimeChanged(event) || reloadedPluginIds(event).includes(pluginId);
}

/** Roster changes refresh availability without replacing a runtime generation. */
export function pluginRosterChanged(event: BridgeEvent) {
  return event.method === "plugins.changed" || event.method === "plugins.reloaded" || pluginRuntimeChanged(event);
}
