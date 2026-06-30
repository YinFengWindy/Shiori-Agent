import { contextBridge, ipcRenderer } from "electron";
import type { BridgeEvent, DesktopApi, WindowControlAction, WindowState } from "./shared.js";

const api: DesktopApi = {
  invoke(request) {
    return ipcRenderer.invoke("desktop:invoke", request) as Promise<import("./shared.js").BridgeResponse>;
  },
  onEvent(listener) {
    const wrapped = (_event: unknown, payload: unknown) => listener(payload as BridgeEvent);
    ipcRenderer.on("desktop:event", wrapped);
    return () => ipcRenderer.off("desktop:event", wrapped);
  },
  pickImages(options) {
    return ipcRenderer.invoke("desktop:pick-images", options) as Promise<string[]>;
  },
  bridgeStatus() {
    return ipcRenderer.invoke("desktop:bridge-status") as Promise<{ running: boolean; lastError: string | null }>;
  },
  restartBridge() {
    return ipcRenderer.invoke("desktop:bridge-restart") as Promise<{ ok: boolean; running: boolean; lastError: string | null }>;
  },
  readSettings() {
    return ipcRenderer.invoke("desktop:settings-read") as Promise<import("./shared.js").SettingsSnapshot>;
  },
  saveSettings(formData) {
    return ipcRenderer.invoke("desktop:settings-save", formData) as Promise<import("./shared.js").SaveSettingsResult>;
  },
  readChannelRoleBindings() {
    return ipcRenderer.invoke("desktop:channel-role-bindings-read") as Promise<import("./shared.js").SettingsBindingsSnapshot>;
  },
  saveChannelRoleBindings(bindings) {
    return ipcRenderer.invoke("desktop:channel-role-bindings-save", bindings) as Promise<import("./shared.js").SettingsBindingsSnapshot>;
  },
  windowControl(action: WindowControlAction) {
    return ipcRenderer.invoke("desktop:window-control", action) as Promise<void>;
  },
  windowState() {
    return ipcRenderer.invoke("desktop:window-state") as Promise<WindowState>;
  },
  smoke() {
    return ipcRenderer.invoke("desktop:smoke") as Promise<{
      status: { running: boolean; lastError: string | null };
      health: import("./shared.js").BridgeResponse;
      roles: import("./shared.js").BridgeResponse;
      restarted: { ok: boolean; running: boolean; lastError: string | null };
      healthAfterRestart: import("./shared.js").BridgeResponse;
      createdRole: import("./shared.js").BridgeResponse;
      openedSession: import("./shared.js").BridgeResponse;
      deletedRole: import("./shared.js").BridgeResponse;
    }>;
  },
};

contextBridge.exposeInMainWorld("miraDesktop", api);
