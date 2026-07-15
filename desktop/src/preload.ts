import { contextBridge, ipcRenderer } from "electron";
import type { BridgeEvent, DesktopApi, RendererDiagnosticPayload, WindowControlAction, WindowState } from "./shared.js";

window.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof Element)) {
    return;
  }
  const anchor = target.closest("a");
  if (!anchor?.href.startsWith("mira-asset:")) {
    return;
  }
  event.preventDefault();
  void ipcRenderer.invoke("desktop:open-attachment", { url: anchor.href });
});

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
  pickChatAttachments(options) {
    return ipcRenderer.invoke("desktop:pick-chat-attachments", options) as Promise<string[]>;
  },
  startAttachmentDrag(request) {
    ipcRenderer.send("desktop:start-attachment-drag", request);
  },
  openAttachment(request) {
    return ipcRenderer.invoke("desktop:open-attachment", request) as Promise<import("./shared.js").LocalAssetOpenResult>;
  },
  reportRendererDiagnostic(payload: RendererDiagnosticPayload) {
    ipcRenderer.send("desktop:renderer-diagnostic", payload);
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
  windowControl(action: WindowControlAction) {
    return ipcRenderer.invoke("desktop:window-control", action) as Promise<void>;
  },
  windowState() {
    return ipcRenderer.invoke("desktop:window-state") as Promise<WindowState>;
  },
};

contextBridge.exposeInMainWorld("miraDesktop", api);
