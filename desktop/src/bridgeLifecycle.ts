import { BrowserWindow } from "electron";
import type { DesktopBridgeClient } from "./bridgeClient.js";
import type { LocalAssetRegistry } from "./localAssetRegistry.js";
import type { BridgeEvent, LocalAssetTransport } from "./shared.js";

/** Starts the Python bridge process and logs startup failures at the app boundary. */
export async function startBridge(bridge: DesktopBridgeClient): Promise<void> {
  try {
    await bridge.start();
  } catch (error) {
    console.error("[desktop] bridge start failed", error);
  }
}

/** Forwards bridge events to every open renderer window. */
export function wireBridgeEvents(
  bridge: DesktopBridgeClient,
  localAssets: LocalAssetRegistry,
): void {
  bridge.on("event", (payload) => {
    const transport: LocalAssetTransport<BridgeEvent> = {
      value: payload,
      assets: localAssets.grantTrustedPayload(payload.payload),
    };
    for (const window of BrowserWindow.getAllWindows()) {
      window.webContents.send("desktop:event", transport);
    }
  });
  bridge.on("exit", (message) => {
    const transport: LocalAssetTransport<BridgeEvent> = {
      value: {
        id: "bridge-exit",
        type: "event",
        method: "bridge.exit",
        payload: { message },
      },
      assets: [],
    };
    for (const window of BrowserWindow.getAllWindows()) {
      window.webContents.send("desktop:event", transport);
    }
  });
}
