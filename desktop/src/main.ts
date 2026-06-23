import { mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { app, BrowserWindow } from "electron";
import { DesktopBridgeClient } from "./bridgeClient.js";
import { startBridge, wireBridgeEvents } from "./bridgeLifecycle.js";
import { registerDesktopIpc } from "./ipc.js";
import { desktopRoot } from "./paths.js";
import { createDesktopWindow } from "./window.js";

const bridge = new DesktopBridgeClient();

function configureUserDataPath(): void {
  const requestedUserDataDir = process.env.MIRA_DESKTOP_USER_DATA_DIR;
  const needsIsolatedSmokeData =
    process.env.MIRA_DESKTOP_SMOKE === "1" || process.env.MIRA_DESKTOP_UI_SMOKE === "1";
  if (!requestedUserDataDir && !needsIsolatedSmokeData) {
    return;
  }
  const userDataDir =
    requestedUserDataDir
      ? resolve(requestedUserDataDir)
      : resolve(tmpdir(), "mira-desktop-smoke", String(process.pid));
  mkdirSync(userDataDir, { recursive: true });
  app.setPath("userData", userDataDir);
}

configureUserDataPath();

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
