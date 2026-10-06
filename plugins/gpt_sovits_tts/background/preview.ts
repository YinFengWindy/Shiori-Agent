import { errorMessage, type BackgroundCtx, type NativeAudio } from "@yinfengwindy/shiori-sdk";
import type { PreviewState } from "../shared/contracts";

/** Owns only acknowledged playback; the requesting editor owns synthesis and stale-result checks. */
export class VoicePreviewController {
  private revision = 0;
  private disposed = false;
  private state: PreviewState = { id: "", role_id: "", phase: "idle", error: "" };
  constructor(private readonly ctx: Pick<BackgroundCtx, "native">) {}

  /** Acknowledges immediately; playback duration never occupies a background rendezvous. */
  play(id: string, roleId: string, audio: NativeAudio) {
    if (this.disposed) throw new Error("试听后台已关闭");
    if (!id || !roleId) throw new Error("试听标识或角色无效");
    const revision = ++this.revision;
    this.state = { id, role_id: roleId, phase: "playing", error: "" };
    void this.run(revision, audio);
    return this.snapshot();
  }

  /** Returns a detached status so editors can observe native playback completion. */
  snapshot() { return { ...this.state }; }

  /** Stale editors may only stop their own preview, never a newer editor's playback. */
  async stop(id: string) {
    if (id !== this.state.id) return this.snapshot();
    this.revision += 1;
    this.state = { ...this.state, phase: "idle", error: "" };
    await this.ctx.native.audio.stop();
    return this.snapshot();
  }

  /** Invalidates pending playback before native resources are reclaimed on plugin unload. */
  async dispose() {
    this.disposed = true;
    await this.stop(this.state.id);
  }

  private async run(revision: number, audio: NativeAudio) {
    const current = () => !this.disposed && revision === this.revision;
    try {
      await this.ctx.native.audio.stop();
      if (!current()) return;
      await this.ctx.native.audio.play(audio);
      if (current()) this.state = { ...this.state, phase: "idle" };
    } catch (cause) {
      if (current()) this.state = { ...this.state, phase: "error", error: errorMessage(cause) };
    }
  }
}
