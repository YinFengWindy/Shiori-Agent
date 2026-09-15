import { contextBridge, ipcRenderer } from "electron";
import { PreloadLocalAssetCache } from "./assets/preloadLocalAssetCache.js";
import { localAssetScheme } from "./assets/localAssetContract.js";
import {
  surfaceMessageChannel,
  surfacePositionChannel,
  surfaceSettledChannel,
  surfaceStateChannel,
} from "./surface/host.js";
import { surfaceChannels } from "./surface/ipc.js";
import { pluginDataChannels } from "./plugins/ipc.js";
import { trayChannels } from "./tray/ipc.js";
import type {
  BridgeEvent,
  BridgeResponse,
  DesktopApi,
  LocalAssetTransport,
  RendererDiagnosticPayload,
  SurfaceCreateResultPayload,
  SurfacePlacementPayload,
  SurfaceSettledPayload,
  TrayEntryClickedPayload,
  WindowControlAction,
  WindowState,
  VoiceInputDevice,
  VoicePlaybackCommand,
} from "./bridge/shared.js";

/**
 * Guards a placement push before it reaches plugin code.
 *
 * The preload is the last place that can reject a malformed main-process
 * payload with the renderer's own types still intact, and a surface renderer
 * lays itself out from these numbers — a NaN reaching it produces an
 * invisible, unclickable window rather than a visible error.
 */
function isSurfacePlacement(value: unknown): value is SurfacePlacementPayload {
  if (value === null || typeof value !== "object") return false;
  const { anchor, bodyOffset, workArea } = value as Record<string, unknown>;
  return isFinitePoint(anchor) && isFinitePoint(bodyOffset) && isFiniteRect(workArea);
}

function isFinitePoint(value: unknown): boolean {
  if (value === null || typeof value !== "object") return false;
  const { x, y } = value as Record<string, unknown>;
  return Number.isFinite(x) && Number.isFinite(y);
}

function isFiniteRect(value: unknown): boolean {
  if (!isFinitePoint(value)) return false;
  const { width, height } = value as Record<string, unknown>;
  return Number.isFinite(width) && Number.isFinite(height);
}

/**
 * Guards a tray click before it reaches a plugin's background code.
 *
 * A click carries no numbers to corrupt, but it does carry whose handler runs:
 * an empty or non-string id would silently match no plugin, turning a menu item
 * the user just clicked into a no-op with nothing logged anywhere.
 */
function isTrayEntryClicked(value: unknown): value is TrayEntryClickedPayload {
  if (value === null || typeof value !== "object") return false;
  const { pluginId, entryId } = value as Record<string, unknown>;
  return typeof pluginId === "string" && Boolean(pluginId)
    && typeof entryId === "string" && Boolean(entryId);
}

/**
 * Guards a settle push before it reaches a plugin's background code.
 *
 * Same reasoning as `isSurfacePlacement`, with a longer fuse: a background
 * module *persists* these coordinates and replays them on the next launch, so a
 * NaN slipping through would not fail visibly now — it would open a window
 * somewhere impossible days later.
 */
function isSurfaceSettled(value: unknown): value is SurfaceSettledPayload {
  if (value === null || typeof value !== "object") return false;
  const { pluginId, surfaceId, placement, reason, displayId } = value as Record<string, unknown>;
  return typeof pluginId === "string" && Boolean(pluginId)
    && typeof surfaceId === "string" && Boolean(surfaceId)
    && typeof reason === "string"
    && typeof displayId === "string"
    && isSurfacePlacement(placement);
}

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
  updates: {
    getState: () => ipcRenderer.invoke("desktop:update-state"),
    check: () => ipcRenderer.invoke("desktop:update-check"),
    install: () => ipcRenderer.invoke("desktop:update-install"),
    onState(listener) {
      const wrapped = (_event: unknown, state: import("./updateContract.js").DesktopUpdateState) => listener(state);
      ipcRenderer.on("desktop:update-state", wrapped);
      return () => ipcRenderer.off("desktop:update-state", wrapped);
    },
  },
  applicationSessionId() {
    return ipcRenderer.invoke("desktop:application-session-id") as Promise<string>;
  },
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
  pickRoleCard() {
    return (ipcRenderer.invoke("desktop:pick-role-card") as Promise<LocalAssetTransport<string[]>>)
      .then((transport) => localAssets.consume(transport)[0] ?? null);
  },
  pickChatAttachments(options) {
    return (ipcRenderer.invoke("desktop:pick-chat-attachments", options) as Promise<LocalAssetTransport<string[]>>)
      .then((transport) => localAssets.consume(transport));
  },
  openExternal(url) {
    return ipcRenderer.invoke("desktop:open-external", { url }) as Promise<import("./bridge/shared.js").ExternalLinkOpenResult>;
  },
  pickFiles(options) {
    return ipcRenderer.invoke("desktop:pick-files", options) as Promise<string[]>;
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
  saveSettings(formData, options) {
    return ipcRenderer.invoke("desktop:settings-save", formData, options) as Promise<import("./bridge/shared.js").SaveSettingsResult>;
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
  // The pet's own drag, sprite, bubble and menu channels are gone: since #181-B
  // the pet is a plugin surface and uses the generic `surface` API below.
  surfaces: {
    create(pluginId, surfaceId, spec, anchor) {
      return ipcRenderer.invoke(surfaceChannels.create, {
        pluginId, surfaceId, spec, x: anchor.x, y: anchor.y,
      }) as Promise<SurfaceCreateResultPayload>;
    },
    destroy(pluginId, surfaceId) {
      return ipcRenderer.invoke(surfaceChannels.destroy, { pluginId, surfaceId }) as Promise<void>;
    },
    show(pluginId, surfaceId) {
      ipcRenderer.send(surfaceChannels.show, { pluginId, surfaceId });
    },
    hide(pluginId, surfaceId) {
      ipcRenderer.send(surfaceChannels.hide, { pluginId, surfaceId });
    },
    workArea(pluginId, surfaceId) {
      return ipcRenderer.invoke(surfaceChannels.workArea, { pluginId, surfaceId }) as Promise<
        SurfacePlacementPayload["workArea"]
      >;
    },
    setPosition(pluginId, surfaceId, position) {
      ipcRenderer.send(surfaceChannels.setPosition, { pluginId, surfaceId, x: position.x, y: position.y });
    },
    moveTo(pluginId, surfaceId, position, durationMs) {
      ipcRenderer.send(surfaceChannels.moveTo, {
        pluginId, surfaceId, x: position.x, y: position.y, durationMs,
      });
    },
    post(pluginId, surfaceId, message) {
      ipcRenderer.send(surfaceChannels.post, { pluginId, surfaceId, message });
    },
    setState(pluginId, surfaceId, state) {
      ipcRenderer.send(surfaceChannels.setState, { pluginId, surfaceId, state });
    },
  },
  surface: {
    beginDrag(offset) {
      ipcRenderer.send(surfaceChannels.beginDrag, { offsetX: offset.x, offsetY: offset.y });
    },
    endDrag(velocity) {
      ipcRenderer.send(surfaceChannels.endDrag, velocity
        ? { velocityX: velocity.x, velocityY: velocity.y }
        : {});
    },
    setExtension(extension) {
      ipcRenderer.send(surfaceChannels.setExtension, extension);
    },
    setClickThrough(clickThrough) {
      ipcRenderer.send(surfaceChannels.setClickThrough, { clickThrough });
    },
    onPlacement(listener) {
      const wrapped = (_event: unknown, payload: unknown) => {
        if (isSurfacePlacement(payload)) listener(payload);
      };
      ipcRenderer.on(surfacePositionChannel, wrapped);
      return () => ipcRenderer.off(surfacePositionChannel, wrapped);
    },
    onMessage(listener) {
      const wrapped = (_event: unknown, payload: unknown) => listener(payload);
      ipcRenderer.on(surfaceMessageChannel, wrapped);
      return () => ipcRenderer.off(surfaceMessageChannel, wrapped);
    },
    onState(listener) {
      const wrapped = (_event: unknown, payload: unknown) => listener(payload);
      ipcRenderer.on(surfaceStateChannel, wrapped);
      return () => ipcRenderer.off(surfaceStateChannel, wrapped);
    },
    ready() {
      ipcRenderer.send(surfaceChannels.ready, {});
    },
    showContextMenu(items) {
      return ipcRenderer.invoke(surfaceChannels.contextMenu, { items }) as Promise<string | null>;
    },
    activateMainWindow() {
      ipcRenderer.send(surfaceChannels.activateMainWindow, {});
    },
  },
  onSurfaceSettled(listener) {
    const wrapped = (_event: unknown, payload: unknown) => {
      if (isSurfaceSettled(payload)) listener(payload);
    };
    ipcRenderer.on(surfaceSettledChannel, wrapped);
    return () => ipcRenderer.off(surfaceSettledChannel, wrapped);
  },
  tray: {
    setEntry(pluginId, entryId, entry) {
      ipcRenderer.send(trayChannels.setEntry, { pluginId, entryId, ...entry });
    },
    removeEntry(pluginId, entryId) {
      ipcRenderer.send(trayChannels.removeEntry, { pluginId, entryId });
    },
    removeAllEntries(pluginId) {
      ipcRenderer.send(trayChannels.removeAllEntries, { pluginId });
    },
    onEntryClicked(listener) {
      const wrapped = (_event: unknown, payload: unknown) => {
        if (isTrayEntryClicked(payload)) listener(payload);
      };
      ipcRenderer.on(trayChannels.entryClicked, wrapped);
      return () => ipcRenderer.off(trayChannels.entryClicked, wrapped);
    },
  },
  pluginData: {
    read(pluginId) {
      return ipcRenderer.invoke(pluginDataChannels.read, { pluginId }) as Promise<unknown>;
    },
    write(pluginId, value) {
      return ipcRenderer.invoke(pluginDataChannels.write, { pluginId, value }) as Promise<void>;
    },
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
