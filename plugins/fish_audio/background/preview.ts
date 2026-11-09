import { errorMessage, type BackgroundCtx, type NativeAudio } from "@yinfengwindy/shiori-sdk";
import type { PreviewState } from "../shared/contracts";

/** Owns only Fish's standalone preview playback, never consumer speech queues. */
export class PreviewPlayer {
  private revision = 0;
  private disposed = false;
  private state: PreviewState = { id: "", phase: "idle", error: "" };
  constructor(private readonly audio: BackgroundCtx["native"]["audio"]) {}

  /** Return promptly while native playback runs for its actual duration. */
  play(id: string, audio: NativeAudio) {
    if (this.disposed) throw new Error("Fish Audio 试听已关闭");
    if (!id) throw new Error("试听标识无效");
    const revision = ++this.revision;
    this.state = { id, phase: "playing", error: "" };
    void this.run(revision, audio);
    return this.snapshot();
  }
  /** Expose current playback completion/error to the editor. */
  snapshot() { return { ...this.state }; }

  /** Only the editor that owns the current preview may stop it. */
  async stop(id: string) {
    if (id !== this.state.id) return this.snapshot();
    this.revision++;
    this.state = { ...this.state, phase: "idle", error: "" };
    await this.audio.stop();
    return this.snapshot();
  }
  /** Invalidate pending native startup before releasing the plugin. */
  async dispose() { this.disposed = true; await this.stop(this.state.id); }

  private async run(revision: number, audio: NativeAudio) {
    const current = () => !this.disposed && revision === this.revision;
    try {
      await this.audio.stop();
      if (!current()) return;
      await this.audio.play(audio);
      if (current()) this.state = { ...this.state, phase: "idle" };
    } catch (cause) {
      if (current()) this.state = { ...this.state, phase: "error", error: errorMessage(cause) };
    }
  }
}
