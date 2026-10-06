import { randomUUID } from "node:crypto";
import type { NativeAudio, PluginNativeContext } from "@yinfengwindy/shiori-sdk/contract";
import type { BrowserVoiceRecorder } from "../voice/recorder.js";
import type { NativeAudioPlayer } from "./audioPlayer.js";
import type { PluginGlobalKeys } from "./globalKeys.js";
import { parseHotkey } from "./hotkey.js";

/** Native session authorization comes from the backend context registry and actual sender. */
export type NativeSessionOptions = {
  isBackground(sender: number): boolean;
  authorize(context: PluginNativeContext): Promise<{ plugin_id: string; generation: string }>;
  recorder: Pick<BrowserVoiceRecorder, "start" | "stop" | "cancel" | "listInputDevices" | "dispose">;
  player: Pick<NativeAudioPlayer, "play" | "stop" | "dispose">;
  keys: Pick<PluginGlobalKeys, "register" | "release">;
  keyEvent(sender: number, token: string, id: string, phase: "down" | "up"): void;
};

/** Tokens bind resources to one admitted plugin context and one real background window. */
export class PluginNativeSessions {
  private readonly sessions = new Map<string, { sender: number; context: PluginNativeContext; captureEpoch: number; playEpoch: number; keyEpochs: Map<string, number> }>();
  private capture: { token: string } | null = null;
  private playback: { token: string } | null = null;
  private revision = 0;
  constructor(private readonly options: NativeSessionOptions) {}

  async open(sender: number, context: PluginNativeContext) {
    if (!this.options.isBackground(sender)) throw new Error("原生能力仅供插件后台使用");
    const revision = this.revision;
    const approved = await this.options.authorize(context);
    if (revision !== this.revision || !this.options.isBackground(sender) || approved.plugin_id !== context.plugin_id || approved.generation !== context.generation) throw new Error("插件运行实例已失效");
    const token = randomUUID();
    this.sessions.set(token, { sender, context, captureEpoch: 0, playEpoch: 0, keyEpochs: new Map() });
    return token;
  }

  /** Resolves ownership before every operation; callers cannot name another plugin. */
  async call(sender: number, token: string, method: string, payload: Record<string, unknown> = {}): Promise<unknown> {
    const session = this.sessions.get(token);
    if (!session && method === "close" && this.options.isBackground(sender)) return;
    if (!session || session.sender !== sender || !this.options.isBackground(sender)) throw new Error("原生资源所有者已失效");
    if (method === "close") { this.close(token); return; }
    const captureEpoch = session.captureEpoch; const playEpoch = session.playEpoch;
    const keyId = String(payload.id ?? ""); const keyEpoch = session.keyEpochs.get(keyId) ?? 0;
    if (method === "keys.unregister") session.keyEpochs.set(keyId, keyEpoch + 1);
    if (method === "audio.capture.cancel") session.captureEpoch += 1;
    if (method === "audio.stop") session.playEpoch += 1;
    if (!["audio.stop", "audio.capture.cancel", "audio.capture.stop", "keys.unregister"].includes(method)) {
      await this.options.authorize(session.context);
      if (this.sessions.get(token) !== session) throw new Error("插件运行实例已失效");
      if (method === "audio.start" && captureEpoch !== session.captureEpoch || method === "audio.play" && playEpoch !== session.playEpoch) throw new Error("原生操作已取消");
      if (method === "keys.register" && keyEpoch !== (session.keyEpochs.get(keyId) ?? 0)) throw new Error("按键注册已取消");
    }
    if (method === "audio.devices") return this.options.recorder.listInputDevices();
    if (method === "audio.start") {
      if (this.capture) throw new Error("麦克风已被占用");
      const operation = { token }; this.capture = operation;
      try { await this.options.recorder.start(String(payload.deviceId ?? "")); }
      catch (error) { if (this.capture === operation) this.capture = null; throw error; }
      if (this.capture !== operation || this.sessions.get(token) !== session) throw new Error("录音操作已取消");
      return;
    }
    if (method === "audio.capture.cancel" || method === "audio.capture.stop") {
      const operation = this.capture;
      if (operation && operation.token !== token) throw new Error("不能停止其他插件的录音");
      if (!operation) { if (method.endsWith("cancel")) return; throw new Error("麦克风尚未启动"); }
      try {
        if (method.endsWith("cancel")) return await this.options.recorder.cancel();
        const audio = await this.options.recorder.stop();
        if (this.capture !== operation || this.sessions.get(token) !== session) throw new Error("录音操作已取消");
        return { audio_base64: Buffer.from(audio).toString("base64"), format: "wav" };
      } finally { if (this.capture === operation) this.capture = null; }
    }
    if (method === "audio.play") {
      if (this.playback) throw new Error("音频播放已被占用");
      if (typeof payload.audio_base64 !== "string" || !payload.audio_base64 || (payload.format !== "wav" && payload.format !== "mp3")) throw new Error("音频格式无效");
      const audio: NativeAudio = { audio_base64: payload.audio_base64, format: payload.format };
      const operation = { token }; this.playback = operation;
      try { await this.options.player.play(audio); }
      finally { if (this.playback === operation) this.playback = null; }
      return;
    }
    if (method === "audio.stop") {
      if (this.playback && this.playback.token !== token) throw new Error("不能停止其他插件的音频");
      if (this.playback?.token === token) { this.options.player.stop(); this.playback = null; }
      return;
    }
    if (method === "keys.register") {
      this.options.keys.register(token, String(payload.id ?? ""), String(payload.accelerator ?? ""), (phase) => {
        if (this.sessions.get(token) === session) this.options.keyEvent(sender, token, String(payload.id), phase);
      }); return;
    }
    if (method === "keys.validate") {
      if (typeof payload.accelerator !== "string" || !parseHotkey(payload.accelerator)) throw new Error("快捷键格式无效");
      return;
    }
    if (method === "keys.unregister") { this.options.keys.release(token, String(payload.id)); return; }
    throw new Error("未知原生操作");
  }

  /** Revokes just these tokens; a late close cannot affect a successor with the same plugin ID. */
  revoke(pluginId?: string) {
    this.revision += 1;
    for (const [token, session] of this.sessions) if (!pluginId || session.context.plugin_id === pluginId) this.close(token);
    if (!pluginId) { this.options.recorder.dispose(); this.options.player.dispose(); }
  }

  private close(token: string) {
    if (!this.sessions.delete(token)) return;
    this.options.keys.release(token);
    if (this.capture?.token === token) { this.capture = null; this.options.recorder.dispose(); }
    if (this.playback?.token === token) { this.playback = null; this.options.player.dispose(); }
    if (!this.sessions.size) this.options.recorder.dispose();
  }
}
