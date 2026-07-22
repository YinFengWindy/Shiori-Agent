import { contextBridge, ipcRenderer } from "electron";
import { PreloadLocalAssetCache } from "./preloadLocalAssetCache.js";
import type {
  BridgeEvent,
  BridgeResponse,
  DesktopApi,
  LocalAssetTransport,
  RendererDiagnosticPayload,
  WindowControlAction,
  WindowState,
} from "./shared.js";

const localAssets = new PreloadLocalAssetCache();

window.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof Element)) {
    return;
  }
  const anchor = target.closest("a");
  if (!anchor?.href.startsWith("shiori-asset:")) {
    return;
  }
  event.preventDefault();
  void ipcRenderer.invoke("desktop:open-attachment", { url: anchor.href });
});

const api: DesktopApi = {
  invoke(request) {
    return (ipcRenderer.invoke("desktop:invoke", request) as Promise<LocalAssetTransport<BridgeResponse>>)
      .then((transport) => localAssets.consume(transport));
  },
  onEvent(listener) {
    const wrapped = (_event: unknown, payload: unknown) => {
      listener(localAssets.consume(payload as LocalAssetTransport<BridgeEvent>));
    };
    ipcRenderer.on("desktop:event", wrapped);
    return () => ipcRenderer.off("desktop:event", wrapped);
  },
  pickImages(options) {
    return (ipcRenderer.invoke("desktop:pick-images", options) as Promise<LocalAssetTransport<string[]>>)
      .then((transport) => localAssets.consume(transport));
  },
  pickChatAttachments(options) {
    return (ipcRenderer.invoke("desktop:pick-chat-attachments", options) as Promise<LocalAssetTransport<string[]>>)
      .then((transport) => localAssets.consume(transport));
  },
  pickPetPackage() {
    return (ipcRenderer.invoke("desktop:pick-pet-package") as Promise<LocalAssetTransport<string[]>>)
      .then((transport) => localAssets.consume(transport)[0] ?? null);
  },
  localAssetUrl(path) {
    return localAssets.resolve(path);
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
  syncPet(forceVisible) {
    return ipcRenderer.invoke("desktop:pet-sync", forceVisible) as Promise<void>;
  },
  beginPetDrag(offsetX, offsetY, screenX, screenY) {
    ipcRenderer.send("desktop:pet-drag-start", { offsetX, offsetY, screenX, screenY });
  },
  movePet(screenX, screenY) {
    ipcRenderer.send("desktop:pet-drag-move", { screenX, screenY });
  },
  endPetDrag() {
    ipcRenderer.send("desktop:pet-drag-end");
  },
  openPetRole() {
    ipcRenderer.send("desktop:pet-open");
  },
  openPetMenu() {
    ipcRenderer.send("desktop:pet-context-menu");
  },
  onPetLoad(listener) {
    ipcRenderer.on("desktop:pet-load", listener);
  },
  offPetLoad(listener) {
    ipcRenderer.off("desktop:pet-load", listener);
  },
  onPetPlay(listener) {
    ipcRenderer.on("desktop:pet-play", listener);
  },
  offPetPlay(listener) {
    ipcRenderer.off("desktop:pet-play", listener);
  },
};

contextBridge.exposeInMainWorld("miraDesktop", api);
