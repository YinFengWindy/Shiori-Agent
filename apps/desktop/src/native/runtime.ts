import { ipcMain, webContents, type BrowserWindow } from "electron";
import type { DesktopBridgeClient } from "../bridge/bridgeClient.js";
import type { BrowserVoiceRecorder } from "../voice/recorder.js";
import { createVoiceCaptureWindow } from "../voice/window.js";
import { registerAudioRendererIpc } from "../voice/ipc.js";
import { NativeAudioPlayer } from "./audioPlayer.js";
import { PluginGlobalKeys } from "./globalKeys.js";
import { PluginNativeSessions } from "./sessions.js";
import { bindNativeDocumentLifecycle } from "./lifecycle.js";

/** Assembles generic audio/key transports around the actual background document. */
export function createNativeRuntime(window: BrowserWindow, bridge: DesktopBridgeClient, recorder: BrowserVoiceRecorder) {
  const player = new NativeAudioPlayer(createVoiceCaptureWindow);
  const sessions = new PluginNativeSessions({
    isBackground: (sender) => !window.isDestroyed() && window.webContents.id === sender,
    authorize: async (context) => {
      const result = await bridge.invoke({ method: "plugins.communication.native.authorize", payload: context });
      if (result.error) throw new Error(result.error.message);
      if (typeof result.payload.plugin_id !== "string" || typeof result.payload.generation !== "string") throw new Error("插件授权响应无效");
      return { plugin_id: result.payload.plugin_id, generation: result.payload.generation };
    },
    recorder, player, keys: new PluginGlobalKeys(),
    keyEvent: (sender, token, id, phase) => webContents.fromId(sender)?.send("desktop:native-key", { token, id, phase }),
  });
  ipcMain.handle("desktop:native-open", (event, context) => sessions.open(event.sender.id, context));
  ipcMain.handle("desktop:native-call", (event, request) => sessions.call(event.sender.id, request.token, request.method, request.payload));
  bindNativeDocumentLifecycle(window.webContents, () => sessions.revoke());
  registerAudioRendererIpc(recorder, player);
  return sessions;
}
