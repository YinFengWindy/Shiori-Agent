import type { BridgeEvent } from "@shiori/plugin-sdk";

/** No-op configuration writes leave existing plugin contexts and requests alive. */
export function pluginRuntimeChanged(event: BridgeEvent) {
  return (event.method === "runtime.applied" && event.payload.changed !== false)
    || event.method === "bridge.exit" || event.method === "bridge.ready";
}
