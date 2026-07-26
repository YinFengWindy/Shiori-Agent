import { readFile, stat } from "node:fs/promises";
import { basename, extname } from "node:path";
import { BrowserWindow, dialog, ipcMain } from "electron";
import type { IpcMainInvokeEvent, OpenDialogOptions } from "electron";
import type { DesktopBridgeClient } from "../bridgeClient.js";
import type { DesktopPetController } from "../pet/controller.js";
import type { DesktopVoiceController } from "./controller.js";
import { isVoiceInteractionBusy } from "./interactionState.js";
import type { BrowserVoicePlayback } from "./playback.js";
import type { BrowserVoiceRecorder } from "./recorder.js";

/** Main-process dependencies needed by the voice-specific IPC boundary. */
export type RegisterVoiceIpcOptions = {
  bridge: DesktopBridgeClient;
  desktopPet: DesktopPetController;
  voiceRecorder: BrowserVoiceRecorder;
  voiceController: DesktopVoiceController;
  voicePlayback: BrowserVoicePlayback;
};

/** Registers capture, testing, cloning, playback, and pet voice IPC handlers. */
export function registerVoiceIpc({
  bridge,
  desktopPet,
  voiceRecorder,
  voiceController,
  voicePlayback,
}: RegisterVoiceIpcOptions): void {
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
    if (voiceTestActive || isVoiceInteractionBusy(voiceController.currentState)) {
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
      provider: String(response.payload.provider || ""),
      ownership: response.payload.ownership === "shiori_managed" ? "shiori_managed" : undefined,
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
}
