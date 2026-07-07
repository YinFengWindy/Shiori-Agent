import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { isAbsolute, resolve } from "node:path";
import { app, BrowserWindow, protocol } from "electron";
import { getLocalAssetMimeType } from "./assetMime.js";
import { DesktopBridgeClient } from "./bridgeClient.js";
import { startBridge, wireBridgeEvents } from "./bridgeLifecycle.js";
import { logDesktopDiagnostic } from "./diagnostics.js";
import { registerDesktopIpc } from "./ipc.js";
import { desktopRoot } from "./paths.js";
import { createDesktopWindow } from "./window.js";

const bridge = new DesktopBridgeClient();
const assetScheme = "mira-asset";

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
      : resolve(tmpdir(), "shiori-desktop-smoke", String(process.pid));
  mkdirSync(userDataDir, { recursive: true });
  app.setPath("userData", userDataDir);
}

configureUserDataPath();

process.on("uncaughtException", (error) => {
  logDesktopDiagnostic({
    scope: "main",
    event: "process.uncaughtException",
    payload: {
      error,
    },
  });
});

process.on("unhandledRejection", (reason) => {
  logDesktopDiagnostic({
    scope: "main",
    event: "process.unhandledRejection",
    payload: {
      reason,
    },
  });
});

app.on("child-process-gone", (_event, details) => {
  logDesktopDiagnostic({
    scope: "main",
    event: "app.child-process-gone",
    payload: {
      type: details.type,
      reason: details.reason,
      exitCode: details.exitCode,
      serviceName: details.serviceName,
      name: details.name,
    },
  });
});

function ensureDesktopConfig(): void {
  const configPath = resolve(desktopRoot, "..", "config.toml");
  if (existsSync(configPath)) {
    return;
  }
  const templatePath = resolve(desktopRoot, "..", "config.example.toml");
  copyFileSync(templatePath, configPath);
}

async function loadLocalAsset(assetPath: string): Promise<Response> {
  if (!isAbsolute(assetPath)) {
    return new Response("asset path must be absolute", { status: 400 });
  }
  const mimeType = getLocalAssetMimeType(assetPath);
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
    return await loadLocalAsset(assetPath);
  });
}

app.whenReady().then(() => {
  ensureDesktopConfig();
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
