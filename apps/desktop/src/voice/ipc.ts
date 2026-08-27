import { BrowserWindow, ipcMain } from "electron";
import type { IpcMainInvokeEvent } from "electron";
import type { DesktopPetController } from "../pet/controller.js";
import type { DesktopVoiceController } from "./controller.js";
import { isVoiceInteractionBusy } from "./interactionState.js";
import type { BrowserVoicePlayback } from "./playback.js";
import type { BrowserVoiceRecorder } from "./recorder.js";

/** Main-process dependencies needed by the voice-specific IPC boundary. */
export type RegisterVoiceIpcOptions = {
  desktopPet: DesktopPetController;
  voiceRecorder: BrowserVoiceRecorder;
  voiceController: DesktopVoiceController;
  voicePlayback: BrowserVoicePlayback;
};

/** Registers capture, testing, playback, and pet voice IPC handlers. */
export function registerVoiceIpc({
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
  let voiceTestStop: Promise<void> | null = null;
  ipcMain.handle("desktop:voice-input-devices-list", async () => {
    return await voiceRecorder.listInputDevices();
  });
  ipcMain.handle("desktop:voice-test-start", async (_event: IpcMainInvokeEvent, deviceId?: unknown) => {
    if (voiceTestActive || voiceTestStop || isVoiceInteractionBusy(voiceController.currentState)) {
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
    if (voiceTestStop) return voiceTestStop;
    if (!voiceTestActive) return;
    voiceTestActive = false;
    voiceTestStop = (async () => {
      const audio = await voiceRecorder.stop();
      await voiceRecorder.playTestAudio(audio);
    })().finally(() => {
      voiceTestStop = null;
    });
    return voiceTestStop;
  });
  ipcMain.handle("desktop:voice-test-cancel", async () => {
    voiceTestActive = false;
    await voiceRecorder.cancel();
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
    voiceController.pointerMoved("pet");
  });
  ipcMain.on("desktop:voice-release", (event) => {
    if (!desktopPet.isPetWindow(BrowserWindow.fromWebContents(event.sender))) return;
    voiceController.release("pet");
  });
  ipcMain.on("desktop:voice-cancel", (event) => {
    if (!desktopPet.isPetWindow(BrowserWindow.fromWebContents(event.sender))) return;
    voiceController.cancel("pet");
  });
}
