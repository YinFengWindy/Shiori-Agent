import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { app, protocol, session, shell, type BrowserWindow } from "electron";
import { localAssetSchemePrivileges, registerLocalAssetProtocol } from "./assetProtocol.js";
import { DesktopBridgeClient } from "./bridgeClient.js";
import { startBridge, wireBridgeEvents } from "./bridgeLifecycle.js";
import { logDesktopDiagnostic } from "./diagnostics.js";
import { registerDesktopIpc } from "./ipc.js";
import { openGrantedLocalAsset } from "./localAssetOpen.js";
import { LocalAssetRegistry, localAssetScheme } from "./localAssetRegistry.js";
import { desktopRoot } from "./paths.js";
import { createDesktopTray } from "./tray.js";
import { attachDesktopWindowLifecycle, createDesktopWindow, showDesktopWindow } from "./window.js";
import { registerDesktopContentSecurityPolicy } from "./windowSecurity.js";

const bridge = new DesktopBridgeClient();
const localAssets = new LocalAssetRegistry();
const trayLifecycleEnabled = process.platform === "win32";
const hasSingleInstanceLock = app.requestSingleInstanceLock();
let desktopWindow: BrowserWindow | null = null;
let desktopTray: ReturnType<typeof createDesktopTray> | null = null;
let isQuitting = false;
let bridgeShutdownStarted = false;

if (!hasSingleInstanceLock) {
  app.quit();
}

protocol.registerSchemesAsPrivileged([
  {
    scheme: localAssetScheme,
    privileges: localAssetSchemePrivileges,
  },
]);

function configureUserDataPath(): void {
  const requestedUserDataDir = process.env.MIRA_DESKTOP_USER_DATA_DIR;
  if (!requestedUserDataDir) {
    return;
  }
  const userDataDir = resolve(requestedUserDataDir);
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

app.on("second-instance", () => {
  logDesktopDiagnostic({
    scope: "main",
    event: "app.second-instance",
    payload: {},
  });
  showOrCreateDesktopWindow();
});

function ensureDesktopConfig(): void {
  const configPath = resolve(desktopRoot, "..", "config.toml");
  if (existsSync(configPath)) {
    return;
  }
  const templatePath = resolve(desktopRoot, "..", "config.example.toml");
  copyFileSync(templatePath, configPath);
}

async function openLocalAttachment(value: string) {
  const result = await openGrantedLocalAsset(localAssets, value, (path) => shell.openPath(path));
  if (result.error) {
    logDesktopDiagnostic({
      scope: "main",
      event: "asset.open.failed",
      payload: { error: result.error },
    });
  }
  return result;
}

function requestAppQuit(): void {
  isQuitting = true;
  app.quit();
}

function shouldHideDesktopWindowOnClose(): boolean {
  return trayLifecycleEnabled && !isQuitting;
}

function wireDesktopWindow(window: BrowserWindow): BrowserWindow {
  attachDesktopWindowLifecycle(window, {
    shouldHideOnClose: shouldHideDesktopWindowOnClose,
  });
  window.on("closed", () => {
    if (desktopWindow === window) {
      desktopWindow = null;
    }
  });
  return window;
}

function getOrCreateDesktopWindow(): BrowserWindow {
  if (desktopWindow) {
    return desktopWindow;
  }
  desktopWindow = wireDesktopWindow(createDesktopWindow({
    openLocalAttachment,
  }));
  return desktopWindow;
}

function showOrCreateDesktopWindow(): BrowserWindow {
  const window = getOrCreateDesktopWindow();
  showDesktopWindow(window);
  return window;
}

void app.whenReady().then(() => {
  ensureDesktopConfig();
  const privateWorkspaceRoot = resolve(app.getPath("home"), ".shiori", "workspace");
  const localAssetImportsRoot = resolve(privateWorkspaceRoot, "private_runtime", "imports");
  localAssets.addTrustedRoot(privateWorkspaceRoot);
  registerDesktopContentSecurityPolicy(
    session.defaultSession.webRequest,
    process.env.MIRA_RENDERER_DEV_SERVER_URL,
  );
  registerLocalAssetProtocol(protocol, localAssets);
  void startBridge(bridge);
  wireBridgeEvents(bridge, localAssets);
  registerDesktopIpc({
    bridge,
    desktopRoot,
    localAssets,
    localAssetImportsRoot,
    openLocalAttachment,
  });
  getOrCreateDesktopWindow();
  if (trayLifecycleEnabled) {
    desktopTray = createDesktopTray({
      onShowWindow: () => {
        showOrCreateDesktopWindow();
      },
      onQuitRequested: requestAppQuit,
    });
  }
  app.on("activate", () => {
    showOrCreateDesktopWindow();
  });
}).catch((error) => {
  logDesktopDiagnostic({
    scope: "main",
    event: "app.whenReady.failed",
    payload: {
      error,
    },
  });
  app.exit(1);
});

app.on("window-all-closed", () => {
  if (!isQuitting && trayLifecycleEnabled) {
    return;
  }
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", (event) => {
  isQuitting = true;
  desktopTray?.destroy();
  if (bridgeShutdownStarted || !bridge.isRunning()) {
    return;
  }
  event.preventDefault();
  bridgeShutdownStarted = true;
  void bridge.stop().finally(() => app.quit());
});

export { bridge };
