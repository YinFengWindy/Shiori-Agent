import type { WebContentsDidStartNavigationEventParams } from "electron";
import type { BridgeEvent } from "@yinfengwindy/shiori-sdk/contract";

/** Window lifecycle subset needed to revoke document-scoped native resources. */
export type NativeLifecycleSource = {
  on(name: "did-start-navigation", listener: (details: WebContentsDidStartNavigationEventParams) => void): unknown;
  on(name: "render-process-gone" | "destroyed", listener: () => void): unknown;
};

/** Same-document navigation preserves resources; reload, crash and closure revoke every token. */
export function bindNativeDocumentLifecycle(source: NativeLifecycleSource, revoke: () => void) {
  source.on("did-start-navigation", (details) => { if (details.isMainFrame && !details.isSameDocument) revoke(); });
  source.on("render-process-gone", revoke);
  source.on("destroyed", revoke);
}

/**
 * Revokes the native sessions a bridge event invalidates: every one when the
 * bridge exits or publishes a new runtime generation, only the reloaded
 * plugins' after an in-generation `plugins.reloaded`.
 */
export function revokeNativeSessionsOnBridgeEvent(event: BridgeEvent, revoke: (pluginId?: string) => void) {
  if (event.method === "bridge.exit" || event.method === "runtime.applied" && event.payload.changed !== false) {
    revoke();
    return;
  }
  const reloaded = event.method === "plugins.reloaded" ? event.payload.plugin_ids : undefined;
  if (!Array.isArray(reloaded)) return;
  for (const pluginId of reloaded) if (typeof pluginId === "string") revoke(pluginId);
}
