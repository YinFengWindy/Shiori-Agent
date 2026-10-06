import type { BrowserWindow, WebContents } from "electron";
import type { NativeAudio } from "@yinfengwindy/shiori-sdk/contract";
import type { VoiceWindowSurface } from "../voice/window.js";
import { createDeferred, type Deferred } from "../voice/deferred.js";

/** Plays exactly one complete audio buffer, with no role, turn or queue policy. */
export class NativeAudioPlayer {
  private window: BrowserWindow | null = null;
  private ready: Promise<void> | null = null;
  private current: { id: string; done: Deferred<void> } | null = null;
  private revision = 0;
  constructor(private readonly createWindow: () => VoiceWindowSurface) {}

  /** Resolves only when playback finishes or is explicitly stopped. */
  async play(audio: NativeAudio) {
    if (this.current) throw new Error("已有音频正在播放");
    if (!audio.audio_base64 || !["wav", "mp3"].includes(audio.format)) throw new Error("音频格式无效");
    const revision = ++this.revision;
    const current = { id: String(revision), done: createDeferred<void>() };
    this.current = current;
    try {
      if (!this.window || this.window.isDestroyed()) {
        const created = this.createWindow(); this.window = created.window; this.ready = created.ready;
        created.window.once("closed", () => {
          if (this.window !== created.window) return;
          this.current?.done.reject(new Error("音频播放窗口已关闭")); this.current = null; this.window = null;
        });
        created.window.webContents.once("render-process-gone", () => {
          if (!created.window.isDestroyed()) created.window.destroy();
        });
      }
      await Promise.race([this.ready, current.done.promise]);
      if (this.current !== current) return;
      this.window!.webContents.send("desktop:voice-playback-command", { command: "play", id: current.id, audioBase64: audio.audio_base64, format: audio.format });
      await current.done.promise;
    } finally { if (this.current === current) this.current = null; }
  }

  /** Stops the active audio immediately; pending decode/load may not start it later. */
  stop() {
    this.current?.done.resolve(undefined); this.current = null; this.revision += 1;
    if (this.window && !this.window.isDestroyed()) this.window.webContents.send("desktop:voice-playback-command", { command: "cancel" });
  }

  /** Accepts terminal acknowledgements only from this player's actual native surface. */
  finish(sender: WebContents, id: string, error?: string) {
    if (!this.window || sender !== this.window.webContents || this.current?.id !== id) return;
    if (error) this.current.done.reject(new Error(error)); else this.current.done.resolve(undefined);
  }

  /** Releases the hidden native window when the owner is deactivated. */
  dispose() { this.stop(); const window = this.window; this.window = null; if (window && !window.isDestroyed()) window.destroy(); }
}
