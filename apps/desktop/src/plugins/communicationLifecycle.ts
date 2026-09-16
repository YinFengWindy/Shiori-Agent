import type { WebContents } from "electron";
import type { DesktopBridgeClient } from "../bridge/bridgeClient.js";

/** Attributes renderer contexts and releases them when a window exits or crashes. */
export function createPluginCommunicationLifecycle(bridge: DesktopBridgeClient) {
  const watched = new Set<number>();
  return (sender: WebContents, request: { method: string; payload: Record<string, unknown> }) => {
    if (request.method !== "plugins.communication.open") return request;
    const renderer = String(sender.id);
    if (!watched.has(sender.id)) {
      watched.add(sender.id);
      const disconnect = () => {
        sender.removeListener("destroyed", disconnect);
        sender.removeListener("render-process-gone", disconnect);
        watched.delete(sender.id);
        if (!bridge.isRunning()) return;
        void bridge.invoke({ method: "plugins.communication.disconnect", payload: { renderer } }).catch((error: unknown) => console.error("[plugin-communication] renderer cleanup failed", error));
      };
      sender.once("destroyed", disconnect);
      sender.once("render-process-gone", disconnect);
    }
    return { ...request, payload: { ...request.payload, renderer } };
  };
}
