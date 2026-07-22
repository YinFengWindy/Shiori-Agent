import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { app, protocol, screen, session, shell, type BrowserWindow } from "electron";
import { localAssetSchemePrivileges, registerLocalAssetProtocol } from "./assetProtocol.js";
import { DesktopBridgeClient } from "./bridgeClient.js";
import { startBridge, wireBridgeEvents } from "./bridgeLifecycle.js";
import { logDesktopDiagnostic } from "./diagnostics.js";
import { registerDesktopIpc } from "./ipc.js";
import { openGrantedLocalAsset } from "./localAssetOpen.js";
import { LocalAssetRegistry, localAssetScheme } from "./localAssetRegistry.js";
import { desktopRoot } from "./paths.js";
import { createDesktopTray } from "./tray.js";
import { createDesktopWindow, showDesktopWindow } from "./window.js";
import {
  attachDesktopWindowLifecycle,
  shouldHideDesktopWindowOnClose as shouldHideDesktopWindowOnClosePolicy,
} from "./windowLifecycle.js";
import { registerDesktopContentSecurityPolicy } from "./windowSecurity.js";
import { DesktopPetController } from "./pet/controller.js";
import { loadDesktopPetSettings, saveDesktopPetSettings } from "./pet/settings.js";
import type { DesktopPetBinding, DesktopPetSettings } from "./pet/types.js";
import { createDesktopPetWindow, displayForDesktopPet } from "./pet/window.js";

const bridge = new DesktopBridgeClient();
const localAssets = new LocalAssetRegistry();
const trayLifecycleEnabled = process.platform === "win32";
const hasSingleInstanceLock = app.requestSingleInstanceLock();
let desktopWindow: BrowserWindow | null = null;
let desktopTray: ReturnType<typeof createDesktopTray> | null = null;
let desktopPetSettings: DesktopPetSettings;
let desktopPet: DesktopPetController | null = null;
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

function desktopPetSettingsPath(): string {
  return resolve(app.getPath("userData"), "desktop-pet.json");
}

async function resolveDesktopPetBinding(roleId?: string): Promise<DesktopPetBinding | null> {
  const response = await bridge.invoke({ method: "roles.list", payload: {} });
  const roles = response.payload.roles;
  if (!Array.isArray(roles)) return null;
  const role = roles.find((item) => item && typeof item === "object" && (roleId ? (item as { id?: unknown }).id === roleId : (item as { desktop_pet_enabled?: unknown }).desktop_pet_enabled === true)) as { id?: unknown; pet_packages?: unknown; selected_pet_package_id?: unknown } | undefined;
  if (!role) return null;
  const packages = role?.pet_packages;
  if (!Array.isArray(packages)) return null;
  const packageId = typeof role?.selected_pet_package_id === "string" ? role.selected_pet_package_id : "";
  const packageValue = packages.find((item) => item && typeof item === "object" && (item as { id?: unknown }).id === packageId) as { id?: unknown; display_name?: unknown; spritesheet_abs?: unknown } | undefined;
  if (!packageValue || typeof packageValue.id !== "string" || typeof packageValue.display_name !== "string" || typeof packageValue.spritesheet_abs !== "string") return null;
  const reference = localAssets.grantPath(packageValue.spritesheet_abs);
  if (!reference) return null;
  if (typeof role.id !== "string") return null;
  return { roleId: role.id, package: { id: packageValue.id, displayName: packageValue.display_name, spritesheetUrl: reference.url } };
}

async function persistDesktopPetSettings(settings: DesktopPetSettings): Promise<void> {
  desktopPetSettings = settings;
  await saveDesktopPetSettings(desktopPetSettingsPath(), settings);
}

function requestAppQuit(): void {
  isQuitting = true;
  app.quit();
}

function shouldHideDesktopWindowOnClose(): boolean {
  return shouldHideDesktopWindowOnClosePolicy({
    isQuitting,
    trayLifecycleEnabled,
    desktopPetRunning: Boolean(desktopPet?.isRunning || desktopPetSettings?.visible),
  });
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
  desktopPetSettings = loadDesktopPetSettings(desktopPetSettingsPath());
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
  desktopPet = new DesktopPetController({
    getSettings: () => desktopPetSettings,
    saveSettings: persistDesktopPetSettings,
    resolveBinding: resolveDesktopPetBinding,
    createWindow: createDesktopPetWindow,
    displayForWindow: displayForDesktopPet,
    getCursorPosition: () => screen.getCursorScreenPoint(),
    openLocalAttachment,
  });
  registerDesktopIpc({
    bridge,
    desktopRoot,
    localAssets,
    localAssetImportsRoot,
    openLocalAttachment,
    desktopPet,
    onOpenDesktopPetRole: showOrCreateDesktopWindow,
  });
  getOrCreateDesktopWindow();
  if (trayLifecycleEnabled) {
    desktopTray = createDesktopTray({
      onShowWindow: () => {
        showOrCreateDesktopWindow();
      },
      onQuitRequested: requestAppQuit,
      getDesktopPetState: () => ({
        visible: desktopPetSettings.visible,
        available: Boolean(desktopPetSettings.roleId && desktopPetSettings.packageId),
      }),
      onToggleDesktopPet: async () => {
        if (!desktopPet) return;
        try {
          await (desktopPetSettings.visible ? desktopPet.hide() : desktopPet.show());
        } catch (error) {
          logDesktopDiagnostic({ scope: "main", event: "desktop-pet.toggle.failed", payload: { error } });
        }
      },
    });
    void desktopPet.restore().catch((error) => {
      logDesktopDiagnostic({ scope: "main", event: "desktop-pet.restore.failed", payload: { error } });
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
