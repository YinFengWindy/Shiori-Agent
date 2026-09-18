import { mkdirSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";
import { app, BrowserWindow, powerMonitor, protocol, session, shell } from "electron";
import { PluginUiResources } from "./plugins/uiResources.js";
import { pluginUiScheme } from "./plugins/uiContract.js";
import { localAssetSchemePrivileges, registerLocalAssetProtocol } from "./assets/assetProtocol.js";
import { DesktopBridgeClient } from "./bridge/bridgeClient.js";
import { startBridge, wireBridgeEvents } from "./bridge/bridgeLifecycle.js";
import { logDesktopDiagnostic } from "./diagnostics.js";
import {
  registerDesktopIpc,
  registerDesktopPluginDataIpc,
  registerDesktopSurfaceIpc,
  registerDesktopTrayIpc,
} from "./bridge/ipc.js";
import { DesktopSurfaceHost, surfaceSettledChannel } from "./surface/host.js";
import {
  createDesktopSurfaceWindow,
  cursorScreenPoint,
  displayIdForSurface,
  showSurfaceContextMenu,
  workAreaForSurface,
} from "./surface/window.js";
import { createPluginHostWindow } from "./pluginHost/window.js";
import { openGrantedLocalAsset } from "./assets/localAssetOpen.js";
import { LocalAssetRegistry, localAssetScheme } from "./assets/localAssetRegistry.js";
import { ensureDesktopRuntimeConfig, resolveDesktopRuntimePaths } from "./runtimePaths.js";
import { registerDesktopUpdates } from "./updater.js";
import { createDesktopTray } from "./tray/menu.js";
import { PluginTrayRegistry } from "./tray/registry.js";
import { trayChannels } from "./tray/ipc.js";
import { createDesktopWindow, showDesktopWindow } from "./window.js";
import {
  attachDesktopWindowLifecycle,
  shouldHideDesktopWindowOnClose as shouldHideDesktopWindowOnClosePolicy,
} from "./windowLifecycle.js";
import { registerDesktopContentSecurityPolicy } from "./windowSecurity.js";
import { PluginDataStore } from "./plugins/dataStore.js";
import {
  desktopPetPluginId,
  desktopPetPresenceChanged,
  desktopPetSurfaceKey,
  isDesktopPetWindow,
  noDesktopPetPresence,
  readDesktopPetPresence,
  type DesktopPetPresence,
} from "./pluginCoupling/desktopPet.js";
import { createVoiceCaptureWindow } from "./voice/window.js";
import { BrowserVoiceRecorder } from "./voice/recorder.js";
import { DesktopVoiceController } from "./voice/controller.js";
import { VoiceHotkeyController } from "./voice/hotkey.js";
import { BrowserVoicePlayback } from "./voice/playback.js";
import { cancelVoiceTurn, createVoicePlaybackCallbacks, handleVoiceBridgeEvent, selectVoiceTurn } from "./voice/bridgeEvents.js";
import { applyVoiceAvailability, isVoiceHotkeyAvailable } from "./voice/availability.js";
import { configureSettingsConfigPath, loadSettingsData } from "./settings.js";
import type {
  BridgeEvent,
  LocalAssetTransport,
  SettingsFormData,
  SurfaceSettledPayload,
  VoiceStatePayload,
} from "./bridge/shared.js";

// Voice replies are played from a trusted hidden renderer without a DOM user gesture.
app.commandLine.appendSwitch("autoplay-policy", "no-user-gesture-required");

// Select the profile before acquiring its single-instance lock.
configureUserDataPath();
const runtimePaths = resolveDesktopRuntimePaths({
  packaged: app.isPackaged,
  appPath: app.getAppPath(),
  homePath: app.getPath("home"),
  workspacePath: process.env.SHIORI_DESKTOP_WORKSPACE,
});
const bridge = new DesktopBridgeClient(runtimePaths.bridge);
// Backend reconnects inherit the same app session; new trust waits for a new app launch.
process.env.SHIORI_DESKTOP_APPLICATION_SESSION_ID = randomUUID();
const localAssets = new LocalAssetRegistry();
const trayLifecycleEnabled = process.platform === "win32";
const hasSingleInstanceLock = app.requestSingleInstanceLock();
let desktopWindow: BrowserWindow | null = null;
let pluginHostWindow: BrowserWindow | null = null;
let desktopTray: ReturnType<typeof createDesktopTray> | null = null;
/**
 * Tray items contributed by plugins (#181-D).
 *
 * Module scope, and created eagerly, because a plugin can contribute an item
 * from its `setup(ctx)` long before the tray itself exists — the plugin-host
 * window is created earlier in `whenReady` than the tray is, and on platforms
 * without a tray lifecycle no `Tray` is ever constructed at all.
 */
const pluginTray = new PluginTrayRegistry();
let desktopSurfaces: DesktopSurfaceHost | null = null;
/** The pet's state as the host sees it; refreshed whenever the plugin writes. */
let desktopPetPresence: DesktopPetPresence = noDesktopPetPresence;
let voiceRecorder: BrowserVoiceRecorder | null = null;
let voiceController: DesktopVoiceController | null = null;
let voicePlayback: BrowserVoicePlayback | null = null;
let voiceHotkey: VoiceHotkeyController | null = null;
let voiceSettings: SettingsFormData["voice"];
let isQuitting = false;
let bridgeShutdownStarted = false;

if (!hasSingleInstanceLock) {
  app.quit();
}

protocol.registerSchemesAsPrivileged([
  { scheme: pluginUiScheme, privileges: { standard: true, secure: true, corsEnabled: true, supportFetchAPI: true } },
  {
    scheme: localAssetScheme,
    privileges: localAssetSchemePrivileges,
  },
]);

function configureUserDataPath(): void {
  const requestedUserDataDir = process.env.SHIORI_DESKTOP_USER_DATA_DIR;
  if (!requestedUserDataDir) {
    return;
  }
  const userDataDir = resolve(requestedUserDataDir);
  mkdirSync(userDataDir, { recursive: true });
  app.setPath("userData", userDataDir);
}

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

/**
 * Where the pet's data lived before plugins had a store.
 *
 * Handed to `PluginDataStore` as a one-off migration source so an existing
 * installation keeps its remembered positions and its visible/hidden choice
 * when the pet's settings move into `plugin-data/desktop_pet.json` (#181-C).
 * Nothing else in the host reads this path.
 */
function legacyPluginDataPath(pluginId: string): string | null {
  if (pluginId !== desktopPetPluginId) return null;
  return resolve(app.getPath("userData"), "desktop-pet.json");
}

/** Publishes host events, such as lock state, for explicit ctx.hostEvents subscriptions. */
function publishDesktopEvent(method: string, payload: Record<string, unknown>): void {
  const transport: LocalAssetTransport<BridgeEvent> = {
    value: { id: `host-${method}-${Date.now()}`, type: "event", method, payload },
    assets: [],
  };
  for (const window of BrowserWindow.getAllWindows()) {
    window.webContents.send("desktop:event", transport);
  }
}

/** Whether the pet's surface window currently exists, asked of the capability that owns it. */
function isDesktopPetRunning(): boolean {
  return Boolean(desktopSurfaces?.has(desktopPetSurfaceKey));
}

function requestAppQuit(): void {
  isQuitting = true;
  app.quit();
}

function publishVoiceState(payload: VoiceStatePayload): void {
  for (const window of BrowserWindow.getAllWindows()) {
    window.webContents.send("desktop:voice-state", payload);
  }
}

function syncVoiceAvailability(cancelCurrentTurn = true): void {
  const hotkey = voiceHotkey;
  if (!hotkey) return;
  const available = isVoiceHotkeyAvailable({
    voiceEnabled: Boolean(voiceSettings?.enabled),
    petRunning: isDesktopPetRunning(),
    petVisible: desktopPetPresence.visible,
  });
  applyVoiceAvailability(available, cancelCurrentTurn, {
    start: () => hotkey.start(),
    stop: () => hotkey.stop(),
    stopAfterCurrentPress: () => hotkey.stopAfterCurrentPress(),
    cancelCurrentTurn: () => voiceController?.cancel(),
  });
}

function reloadVoiceSettings(): void {
  voiceSettings = loadSettingsData().formData.voice;
  voiceHotkey?.setHotkey(voiceSettings.hotkey);
  // Applying settings changes admission of new input; existing voice work keeps its owner.
  syncVoiceAvailability(false);
}

/**
 * Reacts to the pet plugin having written its settings.
 *
 * Since #181-C the host cannot await a pet operation — it publishes a command
 * and the plugin acts on it. This is the other half: the plugin's store write
 * is what tells the host the pet started or stopped, and it lands *after* the
 * surface was created or destroyed, so `isDesktopPetRunning()` is already
 * correct by the time anything here reads it. It also covers changes the host
 * never asked for, which the old `await pet.hide()` path did not.
 *
 * Position writes also pass through here. Only actual presence changes should
 * re-evaluate voice admission; reply state is owned entirely by the plugin.
 *
 * The tray is no longer one of those consumers and is not protected by this
 * guard: since #181-D it follows `PluginTrayRegistry`, which the pet drives
 * from its own side. That path has its own no-change check, in
 * `PluginTrayRegistry.setEntry`.
 */
function handleDesktopPetSettingsChanged(stored: unknown): void {
  const next = readDesktopPetPresence(stored);
  const changed = desktopPetPresenceChanged(desktopPetPresence, next);
  desktopPetPresence = next;
  if (!changed) return;
  // The tray is not refreshed here any more: since #181-D the pet contributes
  // its own item through `ctx.tray` and rewrites its own label, so the menu
  // follows the plugin rather than this mirror. What is left is voice, which
  // still rides on the pet until #221.
  syncVoiceAvailability();
}

function shouldHideDesktopWindowOnClose(): boolean {
  return shouldHideDesktopWindowOnClosePolicy({
    isQuitting,
    trayLifecycleEnabled,
    // Any plugin's surface, not the pet's specifically: closing the shell must
    // not strand a desktop window the user can still see, whoever owns it.
    pluginSurfacesAlive: Boolean(desktopSurfaces?.hasAny()),
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

void app.whenReady().then(async () => {
  ensureDesktopRuntimeConfig(runtimePaths);
  configureSettingsConfigPath(runtimePaths.configPath);
  reloadVoiceSettings();
  process.env.SHIORI_DESKTOP_USER_DATA_DIR = app.getPath("userData");
  // Per-plugin persisted state (#181-C). Read before the tray exists so its
  // "显示桌宠/隐藏桌宠" entry is right on the first paint rather than after the
  // pet plugin's first write.
  const activePluginData = new PluginDataStore({
    directory: resolve(app.getPath("userData"), "plugin-data"),
    legacyPathFor: legacyPluginDataPath,
    onError: (pluginId, operation, error) => {
      logDesktopDiagnostic({ scope: "main", event: "plugin-data.failed", payload: { pluginId, operation, error } });
    },
  });
  registerDesktopPluginDataIpc(activePluginData);
  registerDesktopTrayIpc(pluginTray);
  // Read first, subscribe second. A first-run migration writes through `read`,
  // which would otherwise fire `handleDesktopPetSettingsChanged` before the
  // tray, the hotkey controller exist. They are all null-safe
  // today, so it is harmless today — and it only happens on the one launch
  // where a user upgrades, which is the worst possible place for a latent trap.
  desktopPetPresence = readDesktopPetPresence(await activePluginData.read(desktopPetPluginId));
  activePluginData.onChanged((pluginId, value) => {
    if (pluginId === desktopPetPluginId) handleDesktopPetSettingsChanged(value);
  });
  const activeVoiceRecorder = new BrowserVoiceRecorder(createVoiceCaptureWindow);
  voiceRecorder = activeVoiceRecorder;
  const privateWorkspaceRoot = runtimePaths.workspacePath;
  const localAssetImportsRoot = resolve(privateWorkspaceRoot, "private_runtime", "imports");
  localAssets.addTrustedRoot(privateWorkspaceRoot);
  registerDesktopContentSecurityPolicy(
    session.defaultSession.webRequest,
    process.env.SHIORI_RENDERER_DEV_SERVER_URL,
  );
  registerLocalAssetProtocol(protocol, localAssets);
  const pluginUiResources = new PluginUiResources(resolve(privateWorkspaceRoot, "plugins"));
  protocol.handle(pluginUiScheme, (request) => pluginUiResources.load(request.url));
  void startBridge(bridge);
  const currentVersion = !app.isPackaged && process.env.SHIORI_DEV_VERSION || app.getVersion();
  registerDesktopUpdates(app.isPackaged, currentVersion, (error) => {
    logDesktopDiagnostic({ scope: "main", event: "updater.check.failed", payload: { error } });
  });
  // DesktopSurface (#181). No pet-specific code remains on this side: since
  // #181-C the pet's controller lives in `plugins/desktop_pet/background/` and
  // reaches these primitives over IPC like any other plugin would.
  const activeDesktopSurfaces = new DesktopSurfaceHost({
    createWindow: (key, spec) => createDesktopSurfaceWindow(key, spec, { openLocalAttachment }),
    workAreaFor: workAreaForSurface,
    displayIdFor: displayIdForSurface,
    cursorScreenPoint,
    showContextMenu: showSurfaceContextMenu,
    activateMainWindow: showOrCreateDesktopWindow,
    // Forwarded to the plugin-host renderer rather than handled here: the code
    // that decides whether a settle is worth remembering belongs to whichever
    // plugin owns the surface. Only that window is sent it — it is the only one
    // running `app.background` code, and the surface's own renderer already
    // gets its placement on `surfacePositionChannel`.
    onSettled: (key, placement, reason) => {
      if (!pluginHostWindow || pluginHostWindow.isDestroyed()) return;
      const payload: SurfaceSettledPayload = {
        pluginId: key.pluginId,
        surfaceId: key.surfaceId,
        placement,
        reason,
        displayId: activeDesktopSurfaces.displayId(key),
      };
      pluginHostWindow.webContents.send(surfaceSettledChannel, payload);
    },
  });
  desktopSurfaces = activeDesktopSurfaces;
  registerDesktopSurfaceIpc(activeDesktopSurfaces);
  // Dedicated hidden window for plugin `app.background` code (#226 item 1).
  // Created once here, after the surface IPC it depends on is registered but
  // before any plugin could possibly need it; destroyed in `before-quit`.
  //
  // Side effect worth knowing before touching `window-all-closed` below:
  // because this window is always alive from here to quit, Electron's
  // `window-all-closed` event (which fires only once *every* BrowserWindow
  // is gone) can no longer fire from the main window closing alone — there
  // is always at least this one left. On Windows that is invisible:
  // `trayLifecycleEnabled` is `true`, so the handler below already returns
  // early before checking window count. It would matter on Linux, where
  // `trayLifecycleEnabled` is `false` and that handler currently calls
  // `app.quit()` on this event — closing the main window would no longer
  // quit the app there. The repo only packages Windows today, so this is
  // deliberately left as-is rather than fixed; if Linux/macOS packaging
  // ever happens, this is the first place to revisit.
  pluginHostWindow = createPluginHostWindow({
    onRenderProcessGone: (details) => {
      logDesktopDiagnostic({ scope: "main", event: "plugin-host.render-process-gone", payload: details });
      // Every surface is driven from that renderer (#181-C), so they are all
      // orphaned now: frameless, always-on-top, and nothing left to close them.
      // Reclaiming them is the only thing that keeps the app usable. The
      // plugins themselves stay down until the next launch; recovering them
      // would mean restarting the window and every `setup(ctx)`, which is a
      // bigger change than this one should carry.
      activeDesktopSurfaces.destroyAll();
      // Same reasoning for the tray: every item's click handler lives in that
      // renderer, so leaving them would give the user menu entries that do
      // nothing when clicked.
      pluginTray.clear();
      desktopPetPresence = noDesktopPetPresence;
      syncVoiceAvailability();
    },
  });
  const activeVoiceController = new DesktopVoiceController({
    recorder: activeVoiceRecorder,
    bridge,
    isEnabled: () => Boolean(
      voiceSettings?.enabled
      && isDesktopPetRunning()
      && desktopPetPresence.visible
      && !activeVoiceRecorder.isBusy
    ),
    roleId: () => desktopPetPresence.roleId,
    microphoneDeviceId: () => voiceSettings?.microphoneDeviceId ?? "",
    publishState: publishVoiceState,
    onNewInput: (previousTurnId, nextTurnId) => {
      void selectVoiceTurn(bridge, activeVoicePlayback, previousTurnId, nextTurnId).catch((error) => {
        logDesktopDiagnostic({
          scope: "main",
          event: "voice-turn.cancel.failed",
          payload: { error, previousTurnId, nextTurnId },
        });
      });
    },
    onCancelTurn: (turnId) => {
      activeVoicePlayback.cancelTurn(turnId);
      void cancelVoiceTurn(bridge, turnId).catch((error) => {
        logDesktopDiagnostic({
          scope: "main",
          event: "voice-turn.cancel.failed",
          payload: { error, turnId },
        });
      });
    },
  });
  voiceController = activeVoiceController;
  const activeVoicePlayback = new BrowserVoicePlayback(
    createVoiceCaptureWindow,
    createVoicePlaybackCallbacks(activeVoiceController),
  );
  voicePlayback = activeVoicePlayback;
  if (process.platform === "win32") {
    voiceHotkey = new VoiceHotkeyController({
      onPress: (source) => activeVoiceController.startPress(source),
      onRelease: (source) => activeVoiceController.release(source),
      onCancel: () => activeVoiceController.cancel(),
    });
    voiceHotkey.setHotkey(voiceSettings.hotkey);
  }
  wireBridgeEvents(bridge, localAssets, (event) => {
    if (handleVoiceBridgeEvent(event, activeVoiceController, activeVoicePlayback)) return;
  });
  // The host reports OS availability; plugins own their presentation and behavior.
  powerMonitor.on("lock-screen", () => publishDesktopEvent("system.lock-state", { locked: true }));
  powerMonitor.on("unlock-screen", () => publishDesktopEvent("system.lock-state", { locked: false }));
  registerDesktopIpc({
    bridge,
    pluginUiResources,
    localAssets,
    localAssetImportsRoot,
    openLocalAttachment,
    isPetWindow: (window) => isDesktopPetWindow(activeDesktopSurfaces, window),
    voiceRecorder: activeVoiceRecorder,
    voiceController: activeVoiceController,
    voicePlayback: activeVoicePlayback,
    onVoiceSettingsChanged: reloadVoiceSettings,
    // A plugin that just left the admitted-active roster (disabled, failed,
    // or rolled back by an activation-report failure, #262) must not leave a
    // desktop surface window behind — nothing else in this process is told
    // the plugin stopped, so its window would otherwise sit there forever.
    onPluginDeactivated: (pluginId) => activeDesktopSurfaces.destroyAllForPlugin(pluginId),
  });
  getOrCreateDesktopWindow();
  if (trayLifecycleEnabled) {
    desktopTray = createDesktopTray({
      onShowWindow: () => {
        showOrCreateDesktopWindow();
      },
      onQuitRequested: requestAppQuit,
      pluginEntries: () => pluginTray.list(),
      onPluginEntryClick: (pluginId, entryId) => {
        if (!pluginHostWindow || pluginHostWindow.isDestroyed()) return;
        pluginHostWindow.webContents.send(trayChannels.entryClicked, { pluginId, entryId });
      },
    });
    // The menu follows the registry rather than being rebuilt after a click:
    // what the item should read is the contributing plugin's business, and it
    // may change without anyone touching the tray (the pet hides itself when
    // its binding disappears).
    pluginTray.onChanged(() => desktopTray?.refresh());
    // No `restore()` call here any more: the pet restores itself in its
    // `setup(ctx)` when the plugin host starts it, and tells the host what it
    // decided through its settings write.
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

// Since #226 this fires far less than it reads: the plugin-host window is
// created at startup and lives until quit, so "all windows closed" is no
// longer true merely because the user closed the main window. On Windows that
// is invisible — `trayLifecycleEnabled` is true, so this handler already
// returned early there. On Linux, where the tray lifecycle is off, closing the
// main window would previously have quit the app through here and now will not.
// Nothing packages Linux today; see `createPluginHostWindow`'s call site.
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
  // Nulled, not just destroyed: `pluginTray.onChanged` is never unsubscribed,
  // so a late `setEntry` would otherwise call `setContextMenu` on a destroyed
  // Tray and turn a benign race into a reported failure.
  desktopTray = null;
  if (pluginHostWindow && !pluginHostWindow.isDestroyed()) {
    pluginHostWindow.destroy();
  }
  pluginHostWindow = null;
  voiceHotkey?.stop();
  voiceController?.dispose();
  voicePlayback?.dispose();
  voiceRecorder?.dispose();
  if (bridgeShutdownStarted || !bridge.isRunning()) {
    return;
  }
  event.preventDefault();
  bridgeShutdownStarted = true;
  void (async () => {
    await bridge.stop();
    app.quit();
  })();
});

export { bridge };
