import type { BridgeEvent } from "@yinfengwindy/shiori-sdk";
import { reloadedPluginIds } from "../../../src/shared/pluginsReloaded";
import type { PluginCommunicationEndReason } from "./pluginCommunicationLifetime";

/** No-op configuration writes leave existing plugin contexts and requests alive. */
export function pluginRuntimeChanged(event: BridgeEvent) {
  return (event.method === "runtime.applied" && event.payload.changed !== false)
    || event.method === "bridge.exit" || event.method === "bridge.ready";
}

/** Whether `pluginId`'s communication context belongs to a replaced runtime or instance. */
export function pluginContextReplaced(event: BridgeEvent, pluginId: string) {
  return pluginContextEndReason(event, pluginId) !== undefined;
}

/** Carries the publication's cause through pending calls and retained clients. */
export function pluginContextEndReason(event: BridgeEvent, pluginId: string): PluginCommunicationEndReason | undefined {
  if (event.method === "bridge.exit") return "bridge_exited";
  if (reloadedPluginIds(event).includes(pluginId)) {
    const disabled = event.payload.disabled_plugin_ids;
    return Array.isArray(disabled) && disabled.includes(pluginId) ? "plugin_disabled" : "plugin_reloading";
  }
  if (pluginRuntimeChanged(event)) return "runtime_replaced";
}

/** Roster changes refresh availability without replacing a runtime generation. */
export function pluginRosterChanged(event: BridgeEvent) {
  return event.method === "plugins.changed" || event.method === "plugins.reloaded" || pluginRuntimeChanged(event);
}
