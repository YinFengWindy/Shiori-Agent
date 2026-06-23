import { app, BrowserWindow } from "electron";
import { DesktopBridgeClient } from "./bridgeClient.js";
import { startBridge, wireBridgeEvents } from "./bridgeLifecycle.js";
import { registerDesktopIpc } from "./ipc.js";
import { desktopRoot } from "./paths.js";
import { createDesktopWindow } from "./window.js";

const bridge = new DesktopBridgeClient();

app.whenReady().then(() => {
  void startBridge(bridge);
  wireBridgeEvents(bridge);
  registerDesktopIpc({ bridge, desktopRoot });
  createDesktopWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createDesktopWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  bridge.stop();
});

export { bridge };
