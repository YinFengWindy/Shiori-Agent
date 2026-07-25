import { BrowserWindow, dialog, ipcMain } from "electron";
import { copyFile, mkdir, readFile, stat } from "node:fs/promises";
import { resolve } from "node:path";
import { basename, extname, join } from "node:path";
import { randomUUID } from "node:crypto";
import type { IpcMainInvokeEvent, OpenDialogOptions } from "electron";
import { logDesktopDiagnostic } from "./diagnostics.js";
import type { DesktopBridgeClient } from "./bridgeClient.js";
import { importLocalAssets } from "./localAssetImport.js";
import type { LocalAssetRegistry } from "./localAssetRegistry.js";
import { loadSettingsData, saveSettings } from "./settings.js";
import type { DesktopPetController } from "./pet/controller.js";
import type { DesktopObservationController } from "./observation/controller.js";
import type { BrowserVoiceRecorder } from "./voice/recorder.js";
import type { DesktopVoiceController } from "./voice/controller.js";
import type { BrowserVoicePlayback } from "./voice/playback.js";
import type {
  LocalAssetOpenRequest,
  LocalAssetOpenResult,
  LocalAssetReference,
  LocalAssetTransport,
  RendererDiagnosticPayload,
  SettingsFormData,
} from "./shared.js";
import type { WindowControlAction } from "./shared.js";

type RegisterDesktopIpcOptions = {
  bridge: DesktopBridgeClient;
  desktopRoot: string;
  localAssets: LocalAssetRegistry;
  localAssetImportsRoot: string;
  openLocalAttachment: (value: string) => Promise<LocalAssetOpenResult>;
  desktopPet: DesktopPetController;
  desktopObservation: DesktopObservationController;
  onOpenPetRole: () => void;
  onShowPetContextMenu: (window: BrowserWindow) => void;
  voiceRecorder: BrowserVoiceRecorder;
  voiceController: DesktopVoiceController;
  voicePlayback: BrowserVoicePlayback;
  onVoiceSettingsChanged?: () => void;
  onPetVisibilityChanged?: () => void;
};

function assetTransport<T>(value: T, assets: LocalAssetReference[]): LocalAssetTransport<T> {
  return { value, assets };
}

async function importPickerSelection(
  paths: string[],
  importsRoot: string,
  localAssets: LocalAssetRegistry,
): Promise<LocalAssetTransport<string[]>> {
  const importedPaths = await importLocalAssets(paths, importsRoot);
  const assets: LocalAssetReference[] = [];
  for (const path of importedPaths) {
    const reference = localAssets.grantPath(path);
    if (!reference) {
      throw new Error("imported local asset is outside the trusted workspace");
    }
    assets.push(reference);
  }
  return assetTransport(importedPaths, assets);
}

async function importPetPackageSelection(paths: string[], importsRoot: string): Promise<string[]> {
  const imported: string[] = [];
  for (const source of paths) {
    if (extname(source).toLowerCase() !== ".zip") throw new Error("桌宠包必须是 ZIP 文件");
    const sourceStats = await stat(source);
    if (!sourceStats.isFile() || sourceStats.size > 32 * 1024 * 1024) throw new Error("桌宠包无效或超过 32MB");
    const destinationDirectory = join(importsRoot, "pets");
    await mkdir(destinationDirectory, { recursive: true });
    const destination = join(destinationDirectory, `${randomUUID()}-${basename(source)}`);
    await copyFile(source, destination);
    imported.push(destination);
  }
  return imported;
}

/** Registers all IPC handlers exposed through the desktop preload bridge. */
export function registerDesktopIpc({
  bridge,
  desktopRoot,
  localAssets,
  localAssetImportsRoot,
  openLocalAttachment,
  desktopPet,
  desktopObservation,
  onOpenPetRole,
  onShowPetContextMenu,
  voiceRecorder,
  voiceController,
  voicePlayback,
  onVoiceSettingsChanged,
  onPetVisibilityChanged,
}: RegisterDesktopIpcOptions): void {
  const dragPreviewIconPath = resolve(desktopRoot, "..", "assets", "drag-file-icon.png");

  ipcMain.handle("desktop:invoke", async (_event: IpcMainInvokeEvent, request: { method: string; payload: Record<string, unknown> }) => {
    if (request.method.startsWith("observation.")) {
      throw new Error("observation bridge methods are restricted to the main process");
    }
    const response = await bridge.invoke(request);
    return assetTransport(response, localAssets.grantTrustedPayload(response.payload));
  });
  ipcMain.on("desktop:start-attachment-drag", (event: IpcMainInvokeEvent, request?: { path?: unknown }) => {
    const filePath = String(request?.path ?? "").trim();
    const grant = localAssets.resolveReference(filePath);
    if (!grant) {
      return;
    }
    event.sender.startDrag({
      file: grant.canonicalPath,
      icon: dragPreviewIconPath,
    });
  });
  ipcMain.on("desktop:renderer-diagnostic", (_event: IpcMainInvokeEvent, payload?: RendererDiagnosticPayload) => {
    const diagnostic = payload ?? {
      kind: "error",
      message: "renderer emitted an empty diagnostic payload",
    };
    logDesktopDiagnostic({
      scope: "renderer",
      event: `renderer.${diagnostic.kind}`,
      payload: {
        message: diagnostic.message,
        stack: diagnostic.stack,
        componentStack: diagnostic.componentStack,
        filename: diagnostic.filename,
        lineno: diagnostic.lineno,
        colno: diagnostic.colno,
        details: diagnostic.details ?? {},
      },
    });
  });
  ipcMain.handle("desktop:bridge-status", async () => {
    return {
      running: bridge.isRunning(),
      lastError: bridge.getLastError(),
    };
  });
  ipcMain.handle("desktop:bridge-restart", async () => {
    try {
      await bridge.restart();
      return {
        ok: true,
        running: bridge.isRunning(),
        lastError: bridge.getLastError(),
      };
    } catch (error) {
      return {
        ok: false,
        running: false,
        lastError: String(error),
      };
    }
  });
  ipcMain.handle("desktop:settings-read", async () => {
    return loadSettingsData();
  });
  ipcMain.handle("desktop:settings-save", async (_event: IpcMainInvokeEvent, formData: SettingsFormData) => {
    const result = await saveSettings(
      formData,
      async () => {
        try {
          await bridge.restart();
          return {
            ok: true,
            running: bridge.isRunning(),
            lastError: bridge.getLastError(),
          };
        } catch (error) {
          return {
            ok: false,
            running: false,
            lastError: String(error),
          };
        }
      },
      async () => {
        const health = await bridge.invoke({
          method: "health",
          payload: {},
        });
        return {
          ok: !health.error,
          message: health.error?.message ?? "ok",
        };
      },
    );
    onVoiceSettingsChanged?.();
    return result;
  });
  ipcMain.handle("desktop:window-control", (event: IpcMainInvokeEvent, action: WindowControlAction) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    if (!window) {
      return;
    }
    if (action === "minimize") {
      window.minimize();
      return;
    }
    if (action === "toggleMaximize") {
      if (window.isMaximized()) {
        window.unmaximize();
        return;
      }
      window.maximize();
      return;
    }
    if (action === "close") {
      window.close();
    }
  });
  ipcMain.handle("desktop:window-state", (event: IpcMainInvokeEvent) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    return {
      isMaximized: window?.isMaximized() ?? false,
      isVisible: window?.isVisible() ?? false,
    };
  });
  ipcMain.handle("desktop:pick-images", async (_event: IpcMainInvokeEvent, options?: { multiple?: boolean }) => {
    const result = await dialog.showOpenDialog({
      properties: options?.multiple ? ["openFile", "multiSelections"] : ["openFile"],
      filters: [
        {
          name: "Images",
          extensions: ["png", "jpg", "jpeg", "webp", "gif"],
        },
      ],
    });
    if (result.canceled) {
      return assetTransport([], []);
    }
    return await importPickerSelection(result.filePaths, localAssetImportsRoot, localAssets);
  });
  ipcMain.handle("desktop:pet-sync", async (_event: IpcMainInvokeEvent, forceVisible?: unknown) => {
    await desktopPet.sync(typeof forceVisible === "boolean" ? forceVisible : undefined);
    await desktopObservation.restore();
    onPetVisibilityChanged?.();
  });
  ipcMain.handle("desktop:pet-observation-dismiss", async (event: IpcMainInvokeEvent) => {
    const petWindow = BrowserWindow.fromWebContents(event.sender);
    if (!desktopPet.isPetWindow(petWindow)) return;
    desktopObservation.dismissBubble();
  });
  ipcMain.on("desktop:pet-renderer-ready", (event) => {
    desktopPet.rendererReady(BrowserWindow.fromWebContents(event.sender));
  });
  ipcMain.on("desktop:pet-bubble-height", (event, height: unknown) => {
    const petWindow = BrowserWindow.fromWebContents(event.sender);
    if (!desktopPet.isPetWindow(petWindow)) return;
    desktopPet.setBubbleHeight(Number(height));
  });
  ipcMain.on("desktop:pet-drag-start", (event, payload?: { offsetX?: unknown; offsetY?: unknown; screenX?: unknown; screenY?: unknown }) => {
    const petWindow = BrowserWindow.fromWebContents(event.sender);
    if (!desktopPet.isPetWindow(petWindow)) return;
    desktopPet.beginDrag(
      Number(payload?.offsetX),
      Number(payload?.offsetY),
      Number(payload?.screenX),
      Number(payload?.screenY),
    );
  });
  ipcMain.on("desktop:pet-drag-move", (event, payload?: { screenX?: unknown; screenY?: unknown }) => {
    const petWindow = BrowserWindow.fromWebContents(event.sender);
    if (!desktopPet.isPetWindow(petWindow)) return;
    const screenX = Number(payload?.screenX);
    const screenY = Number(payload?.screenY);
    if (!Number.isFinite(screenX) || !Number.isFinite(screenY)) return;
    desktopPet.moveDrag({ x: screenX, y: screenY });
  });
  ipcMain.on("desktop:pet-drag-end", (event, payload?: {
    screenX?: unknown;
    screenY?: unknown;
    velocityX?: unknown;
    velocityY?: unknown;
  }) => {
    const petWindow = BrowserWindow.fromWebContents(event.sender);
    if (!desktopPet.isPetWindow(petWindow)) return;
    const screenX = Number(payload?.screenX);
    const screenY = Number(payload?.screenY);
    const velocityX = Number(payload?.velocityX);
    const velocityY = Number(payload?.velocityY);
    desktopPet.endDrag(
      Number.isFinite(screenX) && Number.isFinite(screenY) ? { x: screenX, y: screenY } : undefined,
      Number.isFinite(velocityX) && Number.isFinite(velocityY) ? { x: velocityX, y: velocityY } : undefined,
    );
  });
  ipcMain.on("desktop:pet-open", (event) => {
    const petWindow = BrowserWindow.fromWebContents(event.sender);
    if (desktopPet.isPetWindow(petWindow)) onOpenPetRole();
  });
  ipcMain.on("desktop:pet-context-menu", (event) => {
    const petWindow = BrowserWindow.fromWebContents(event.sender);
    if (petWindow && desktopPet.isPetWindow(petWindow)) onShowPetContextMenu(petWindow);
  });
  ipcMain.on("desktop:voice-capture-ready", (event) => {
    voiceRecorder.handleReady(event.sender);
  });
  ipcMain.on("desktop:voice-capture-data", (event, value: unknown) => {
    let data: ArrayBuffer | null = null;
    if (value instanceof ArrayBuffer) {
      data = value;
    } else if (ArrayBuffer.isView(value)) {
      const copied = new Uint8Array(value.byteLength);
      copied.set(new Uint8Array(value.buffer, value.byteOffset, value.byteLength));
      data = copied.buffer;
    }
    if (data) voiceRecorder.handleData(event.sender, data);
  });
  ipcMain.on("desktop:voice-capture-stopped", (event) => {
    voiceRecorder.handleStopped(event.sender);
  });
  ipcMain.on("desktop:voice-capture-error", (event, message: unknown) => {
    voiceRecorder.handleError(event.sender, String(message || "麦克风采集失败"));
  });
  ipcMain.on("desktop:voice-input-devices", (event, devices: unknown) => {
    voiceRecorder.handleInputDevices(event.sender, devices);
  });
  let voiceTestActive = false;
  ipcMain.handle("desktop:voice-input-devices-list", async () => {
    return await voiceRecorder.listInputDevices();
  });
  ipcMain.handle("desktop:voice-test-start", async (_event: IpcMainInvokeEvent, deviceId?: unknown) => {
    if (voiceTestActive || voiceController.currentState.kind !== "idle") {
      throw new Error("当前已有语音任务正在进行");
    }
    voiceTestActive = true;
    try {
      await voiceRecorder.start(typeof deviceId === "string" ? deviceId : "");
    } catch (error) {
      voiceTestActive = false;
      throw error;
    }
  });
  ipcMain.handle("desktop:voice-test-stop", async () => {
    if (!voiceTestActive) return;
    try {
      const audio = await voiceRecorder.stop();
      await voiceRecorder.playTestAudio(audio);
    } finally {
      voiceTestActive = false;
    }
  });
  ipcMain.handle("desktop:voice-clone", async (event: IpcMainInvokeEvent) => {
    const parentWindow = BrowserWindow.fromWebContents(event.sender) ?? undefined;
    const options: OpenDialogOptions = {
      properties: ["openFile"],
      filters: [{ name: "Voice sample", extensions: ["wav", "mp3", "m4a"] }],
    };
    const picked = parentWindow
      ? await dialog.showOpenDialog(parentWindow, options)
      : await dialog.showOpenDialog(options);
    if (picked.canceled || !picked.filePaths[0]) return { ok: false, canceled: true };
    const filePath = picked.filePaths[0];
    const fileStats = await stat(filePath);
    if (!fileStats.isFile() || fileStats.size > 20 * 1024 * 1024) {
      return { ok: false, error: "复刻录音无效或超过 20MB" };
    }
    const extension = extname(filePath).slice(1).toLowerCase();
    if (!["wav", "mp3", "m4a"].includes(extension)) {
      return { ok: false, error: "复刻录音必须是 WAV、MP3 或 M4A" };
    }
    const audio = await readFile(filePath);
    const response = await bridge.invoke({
      method: "voice.clone",
      payload: { audio_base64: audio.toString("base64"), file_name: basename(filePath) },
    });
    if (response.error) return { ok: false, error: response.error.message };
    return {
      ok: true,
      voiceId: String(response.payload.voice_id || ""),
      audioBase64: String(response.payload.audio_base64 || ""),
      format: "mp3",
    };
  });
  ipcMain.handle("desktop:voice-preview", async (_event: IpcMainInvokeEvent, audioBase64?: unknown) => {
    const encoded = String(audioBase64 || "");
    if (!encoded) throw new Error("试听音频为空");
    let audio: Buffer;
    try {
      audio = Buffer.from(encoded, "base64");
    } catch {
      throw new Error("试听音频无效");
    }
    await voiceRecorder.playTestAudio(new Uint8Array(audio));
  });
  ipcMain.on("desktop:voice-playback-started", (event, id: unknown) => {
    voicePlayback.handleStarted(event.sender, String(id || ""));
  });
  ipcMain.on("desktop:voice-playback-finished", (event, id: unknown) => {
    voicePlayback.handleFinished(event.sender, String(id || ""));
  });
  ipcMain.on("desktop:voice-playback-error", (event, value: unknown) => {
    const payload = value && typeof value === "object" ? value as { id?: unknown; message?: unknown } : {};
    voicePlayback.handleError(event.sender, String(payload.id || ""), String(payload.message || "音频播放失败"));
  });
  ipcMain.on("desktop:voice-press-start", (event) => {
    if (!desktopPet.isPetWindow(BrowserWindow.fromWebContents(event.sender))) return;
    voiceController.startPress("pet");
  });
  ipcMain.on("desktop:voice-pointer-moved", (event) => {
    if (!desktopPet.isPetWindow(BrowserWindow.fromWebContents(event.sender))) return;
    voiceController.pointerMoved();
  });
  ipcMain.on("desktop:voice-release", (event) => {
    if (!desktopPet.isPetWindow(BrowserWindow.fromWebContents(event.sender))) return;
    voiceController.release();
  });
  ipcMain.on("desktop:voice-cancel", (event) => {
    if (!desktopPet.isPetWindow(BrowserWindow.fromWebContents(event.sender))) return;
    voiceController.cancel();
  });
  ipcMain.handle("desktop:pick-chat-attachments", async (_event: IpcMainInvokeEvent, options?: { multiple?: boolean }) => {
    const result = await dialog.showOpenDialog({
      properties: options?.multiple ? ["openFile", "multiSelections"] : ["openFile"],
      filters: [
        {
          name: "Chat Attachments",
          extensions: ["png", "jpg", "jpeg", "webp", "gif", "md", "txt"],
        },
      ],
    });
    if (result.canceled) {
      return assetTransport([], []);
    }
    return await importPickerSelection(result.filePaths, localAssetImportsRoot, localAssets);
  });
  ipcMain.handle("desktop:pick-pet-package", async () => {
    const result = await dialog.showOpenDialog({
      properties: ["openFile"],
      filters: [{ name: "Codex Pet Package", extensions: ["zip"] }],
    });
    if (result.canceled) return assetTransport([], []);
    return assetTransport(await importPetPackageSelection(result.filePaths, localAssetImportsRoot), []);
  });
  ipcMain.handle("desktop:open-attachment", async (_event: IpcMainInvokeEvent, request: LocalAssetOpenRequest) => {
    const value = String(request?.url || request?.path || "").trim();
    return await openLocalAttachment(value);
  });
}
