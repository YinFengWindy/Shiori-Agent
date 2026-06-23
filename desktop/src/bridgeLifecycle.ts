import { BrowserWindow } from "electron";
import type { DesktopBridgeClient } from "./bridgeClient.js";

/** Starts the Python bridge process and logs startup failures at the app boundary. */
export async function startBridge(bridge: DesktopBridgeClient): Promise<void> {
  try {
    await bridge.start();
  } catch (error) {
    console.error("[desktop] bridge start failed", error);
  }
}

/** Forwards bridge events to every open renderer window. */
export function wireBridgeEvents(bridge: DesktopBridgeClient): void {
  bridge.on("event", (payload) => {
    for (const window of BrowserWindow.getAllWindows()) {
      window.webContents.send("desktop:event", payload);
    }
  });
  bridge.on("exit", (message) => {
    for (const window of BrowserWindow.getAllWindows()) {
      window.webContents.send("desktop:event", {
        id: "bridge-exit",
        type: "event",
        method: "bridge.exit",
        payload: { message },
      });
    }
  });
}
