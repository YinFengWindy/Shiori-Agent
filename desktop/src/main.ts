import { mkdirSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { extname, isAbsolute, resolve } from "node:path";
import { app, BrowserWindow, protocol } from "electron";
import { DesktopBridgeClient } from "./bridgeClient.js";
import { startBridge, wireBridgeEvents } from "./bridgeLifecycle.js";
import { registerDesktopIpc } from "./ipc.js";
import { desktopRoot } from "./paths.js";
import { createDesktopWindow } from "./window.js";

const bridge = new DesktopBridgeClient();
const assetScheme = "mira-asset";
const assetMimeTypes = new Map([
  [".gif", "image/gif"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".png", "image/png"],
  [".webp", "image/webp"],
]);

protocol.registerSchemesAsPrivileged([
  {
    scheme: assetScheme,
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
    },
  },
]);

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

async function loadLocalImageAsset(assetPath: string): Promise<Response> {
  if (!isAbsolute(assetPath)) {
    return new Response("asset path must be absolute", { status: 400 });
  }
  const mimeType = assetMimeTypes.get(extname(assetPath).toLowerCase());
  if (!mimeType) {
    return new Response("unsupported asset type", { status: 415 });
  }
  const data = await readFile(assetPath);
  return new Response(data, {
    headers: {
      "Content-Type": mimeType,
    },
  });
}

function registerAssetProtocol(): void {
  protocol.handle(assetScheme, async (request) => {
    const requestedUrl = new URL(request.url);
    const assetPath = requestedUrl.searchParams.get("path");
    if (!assetPath) {
      return new Response("missing asset path", { status: 400 });
    }
    return await loadLocalImageAsset(assetPath);
  });
}

app.whenReady().then(() => {
  registerAssetProtocol();
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
