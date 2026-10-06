import { ipcMain } from "electron";
import type { BrowserVoiceRecorder } from "./recorder.js";
import type { NativeAudioPlayer } from "../native/audioPlayer.js";

/** Accepts device acknowledgements only through each native resource owner. */
export function registerAudioRendererIpc(voiceRecorder: BrowserVoiceRecorder, player: NativeAudioPlayer): void {
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

  ipcMain.on("desktop:voice-playback-finished", (event, id: string) => player.finish(event.sender, id));
  ipcMain.on("desktop:voice-playback-error", (event, value: { id: string; message: string }) => player.finish(event.sender, value.id, value.message));
}
