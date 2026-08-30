import { contextBridge, ipcRenderer } from "electron";
import { PreloadLocalAssetCache } from "./assets/preloadLocalAssetCache.js";
import { localAssetScheme } from "./assets/localAssetContract.js";
import type {
  BridgeEvent,
  BridgeResponse,
  DesktopApi,
  LocalAssetTransport,
  RendererDiagnosticPayload,
  WindowControlAction,
  WindowState,
  VoiceInputDevice,
  VoicePlaybackCommand,
} from "./bridge/shared.js";

const localAssets = new PreloadLocalAssetCache();

window.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof Element)) {
    return;
  }
  const anchor = target.closest("a");
  if (!anchor?.href.startsWith(`${localAssetScheme}:`)) {
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
  openExternal(url) {
    return ipcRenderer.invoke("desktop:open-external", { url }) as Promise<import("./bridge/shared.js").ExternalLinkOpenResult>;
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
    return ipcRenderer.invoke("desktop:settings-read") as Promise<import("./bridge/shared.js").SettingsSnapshot>;
  },
  saveSettings(formData) {
    return ipcRenderer.invoke("desktop:settings-save", formData) as Promise<import("./bridge/shared.js").SaveSettingsResult>;
  },
  listVoiceInputDevices() {
    return ipcRenderer.invoke("desktop:voice-input-devices-list") as Promise<VoiceInputDevice[]>;
  },
  startVoiceTest(deviceId) {
    return ipcRenderer.invoke("desktop:voice-test-start", deviceId);
  },
  stopVoiceTest() {
    return ipcRenderer.invoke("desktop:voice-test-stop");
  },
  cancelVoiceTest() {
    return ipcRenderer.invoke("desktop:voice-test-cancel");
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
  dismissPetObservationBubble() {
    return ipcRenderer.invoke("desktop:pet-observation-dismiss") as Promise<void>;
  },
  beginPetDrag(offsetX, offsetY, screenX, screenY) {
    ipcRenderer.send("desktop:pet-drag-start", { offsetX, offsetY, screenX, screenY });
  },
  movePet(screenX, screenY) {
    ipcRenderer.send("desktop:pet-drag-move", { screenX, screenY });
  },
  endPetDrag(screenX, screenY, velocityX, velocityY) {
    ipcRenderer.send("desktop:pet-drag-end", { screenX, screenY, velocityX, velocityY });
  },
  openPetRole() {
    ipcRenderer.send("desktop:pet-open");
  },
  openPetMenu() {
    ipcRenderer.send("desktop:pet-context-menu");
  },
  petRendererReady() {
    ipcRenderer.send("desktop:pet-renderer-ready");
  },
  setPetBubbleHeight(height) {
    ipcRenderer.send("desktop:pet-bubble-height", height);
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
  onPetObservation(listener) {
    ipcRenderer.on("desktop:pet-observation", listener);
  },
  offPetObservation(listener) {
    ipcRenderer.off("desktop:pet-observation", listener);
  },
  onPetBubbleLayout(listener) {
    ipcRenderer.on("desktop:pet-bubble-layout", listener);
  },
  offPetBubbleLayout(listener) {
    ipcRenderer.off("desktop:pet-bubble-layout", listener);
  },
  onVoiceCaptureCommand(listener) {
    const wrapped = (_event: unknown, value: unknown) => {
      if (value === "stop" || value === "cancel") {
        listener(value);
        return;
      }
      if (!value || typeof value !== "object") return;
      const command = value as { command?: unknown; deviceId?: unknown; audioBase64?: unknown };
      if (command.command === "start" && (command.deviceId === undefined || typeof command.deviceId === "string")) {
        listener({ command: "start", deviceId: typeof command.deviceId === "string" ? command.deviceId : undefined });
      } else if (command.command === "list-devices") {
        listener({ command: "list-devices" });
      } else if (command.command === "play-test" && typeof command.audioBase64 === "string") {
        listener({ command: "play-test", audioBase64: command.audioBase64 });
      }
    };
    ipcRenderer.on("desktop:voice-capture-command", wrapped);
    return () => ipcRenderer.off("desktop:voice-capture-command", wrapped);
  },
  voiceCaptureData(samples) {
    ipcRenderer.send("desktop:voice-capture-data", samples);
  },
  voiceCaptureReady() {
    ipcRenderer.send("desktop:voice-capture-ready");
  },
  voiceCaptureStopped() {
    ipcRenderer.send("desktop:voice-capture-stopped");
  },
  voiceCaptureError(message) {
    ipcRenderer.send("desktop:voice-capture-error", message);
  },
  voiceInputDevices(devices: VoiceInputDevice[]) {
    ipcRenderer.send("desktop:voice-input-devices", devices);
  },
  onVoicePlaybackCommand(listener) {
    const wrapped = (_event: unknown, value: unknown) => {
      if (!value || typeof value !== "object") return;
      const command = value as Partial<VoicePlaybackCommand>;
      if (command.command === "cancel") {
        listener({ command: "cancel" });
        return;
      }
      if (command.command === "play" && typeof command.id === "string" && typeof command.audioBase64 === "string" && command.format === "mp3") {
        listener({ command: "play", id: command.id, audioBase64: command.audioBase64, format: "mp3" });
      }
    };
    ipcRenderer.on("desktop:voice-playback-command", wrapped);
    return () => ipcRenderer.off("desktop:voice-playback-command", wrapped);
  },
  voicePlaybackStarted(id) {
    ipcRenderer.send("desktop:voice-playback-started", id);
  },
  voicePlaybackFinished(id) {
    ipcRenderer.send("desktop:voice-playback-finished", id);
  },
  voicePlaybackError(id, message) {
    ipcRenderer.send("desktop:voice-playback-error", { id, message });
  },
  startVoicePress() {
    ipcRenderer.send("desktop:voice-press-start");
  },
  voicePointerMoved() {
    ipcRenderer.send("desktop:voice-pointer-moved");
  },
  voiceRelease() {
    ipcRenderer.send("desktop:voice-release");
  },
  voiceCancel() {
    ipcRenderer.send("desktop:voice-cancel");
  },
  onVoiceState(listener) {
    const wrapped = (_event: unknown, value: unknown) => {
      if (!value || typeof value !== "object") return;
      listener(value as import("./bridge/shared.js").VoiceStatePayload);
    };
    ipcRenderer.on("desktop:voice-state", wrapped);
    return () => ipcRenderer.off("desktop:voice-state", wrapped);
  },
};

contextBridge.exposeInMainWorld("miraDesktop", api);
