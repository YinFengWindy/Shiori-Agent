import { BrowserWindow, dialog, ipcMain, shell, type WebContents } from "electron";
import { logDesktopDiagnostic, openDiagnosticsFolder } from "../diagnostics.js";
import { desktopDragFileIcon } from "../paths.js";
import { registerVoiceIpc } from "../voice/ipc.js";
import {
  registerSurfaceIpc,
  type SurfaceIpcEvent,
  type SurfaceIpcHost,
} from "../surface/ipc.js";
import type { DesktopSurfaceHost } from "../surface/host.js";
import { registerPluginDataIpc } from "../plugins/ipc.js";
import type { PluginDataStore } from "../plugins/dataStore.js";
import { registerTrayIpc } from "../tray/ipc.js";
import type { PluginTrayRegistry } from "../tray/registry.js";
import {
  registerDesktopIpcHandlers,
  type DesktopIpcHost,
  type RegisterDesktopIpcOptions,
} from "./ipcRegistrations.js";

export type { RegisterDesktopIpcOptions };

/** Binds the IPC boundary to the real Electron main process. */
const electronHost: DesktopIpcHost = {
  handle: (channel, listener) => { ipcMain.handle(channel, listener); },
  on: (channel, listener) => { ipcMain.on(channel, listener); },
  windowFromWebContents: (sender) => BrowserWindow.fromWebContents(sender),
  showOpenDialog: (options) => dialog.showOpenDialog(options),
  openExternal: (url) => shell.openExternal(url),
  logDiagnostic: logDesktopDiagnostic,
  openDiagnosticsFolder,
  dragFileIcon: desktopDragFileIcon,
  registerVoiceIpc,
};

/** Binds the DesktopSurface channels to the real Electron main process. */
const electronSurfaceHost: SurfaceIpcHost = {
  handle: (channel, listener) => { ipcMain.handle(channel, listener); },
  on: (channel, listener) => { ipcMain.on(channel, listener); },
  windowIdFromEvent: (event: SurfaceIpcEvent) => {
    const window = BrowserWindow.fromWebContents(event.sender as WebContents);
    return window && !window.isDestroyed() ? window.id : null;
  },
};

/** Registers all IPC handlers exposed through the desktop preload bridge. */
export function registerDesktopIpc(options: RegisterDesktopIpcOptions): void {
  registerDesktopIpcHandlers(electronHost, options);
}

/** Registers the per-plugin data store's channels (#181-C). */
export function registerDesktopPluginDataIpc(store: PluginDataStore): void {
  registerPluginDataIpc(
    { handle: (channel, listener) => { ipcMain.handle(channel, listener); } },
    store,
  );
}

/** Registers the plugin tray capability's channels (#181-D). */
export function registerDesktopTrayIpc(registry: PluginTrayRegistry): void {
  registerTrayIpc(
    {
      on: (channel, listener) => { ipcMain.on(channel, listener); },
      onError: (channel, error) => logDesktopDiagnostic({
        scope: "main",
        event: "tray-request-failed",
        payload: { channel, error: error instanceof Error ? error.message : String(error) },
      }),
    },
    registry,
  );
}

/** Registers the DesktopSurface capability's channels (#181). */
export function registerDesktopSurfaceIpc(surfaces: DesktopSurfaceHost): void {
  registerSurfaceIpc(electronSurfaceHost, {
    surfaces,
    onError: (channel, error) => logDesktopDiagnostic({
      scope: "main",
      event: "surface-request-failed",
      payload: { channel, error: error instanceof Error ? error.message : String(error) },
    }),
  });
}
