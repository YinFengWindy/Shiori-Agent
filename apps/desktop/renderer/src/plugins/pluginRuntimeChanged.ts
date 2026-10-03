import type { BridgeEvent } from "@yinfengwindy/shiori-sdk";

/** No-op configuration writes leave existing plugin contexts and requests alive. */
export function pluginRuntimeChanged(event: BridgeEvent) {
  return (event.method === "runtime.applied" && event.payload.changed !== false)
    || event.method === "bridge.exit" || event.method === "bridge.ready";
}

/** Roster changes refresh availability without replacing a runtime generation. */
export function pluginRosterChanged(event: BridgeEvent) {
  return event.method === "plugins.changed" || pluginRuntimeChanged(event);
}
