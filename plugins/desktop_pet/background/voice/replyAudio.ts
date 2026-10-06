import type { BackgroundCtx, PluginServiceReference, TtsResult } from "@yinfengwindy/shiori-sdk";
import { SpeechSentenceBuffer } from "./sentences";

/** Serial synthesis/playback and cancellation stay in the desktop pet consumer. */
export class PetReplyAudio {
  private epoch = 0;
  private tail = Promise.resolve();
  private buffer = new SpeechSentenceBuffer();
  private text = "";
  constructor(private readonly ctx: Pick<BackgroundCtx, "rpc" | "native">, private readonly status: (status: "speaking_prepare" | "speaking" | "idle" | "error", message?: string) => void) {}
  begin() { this.epoch += 1; this.buffer = new SpeechSentenceBuffer(); this.text = ""; return this.epoch; }
  push(text: string, final: boolean, provider: PluginServiceReference, roleId: string, mood: string) {
    const epoch = this.epoch;
    if (!final) this.text += text;
    const sentences = this.buffer.push(final && !this.text ? text : final ? "" : text, final);
    for (const sentence of sentences) {
      this.tail = this.tail.then(async () => {
        if (epoch !== this.epoch) return;
        this.status("speaking_prepare");
        const result = await this.ctx.rpc.services.call<TtsResult>(provider, "synthesize", { text: sentence, role_id: roleId, mood });
        if (epoch !== this.epoch) return;
        this.status("speaking");
        await this.ctx.native.audio.play(result);
      }).catch((error) => { if (epoch === this.epoch) { this.epoch += 1; this.status("error", error instanceof Error ? error.message : String(error)); } });
    }
    if (final) this.tail = this.tail.then(() => { if (epoch === this.epoch) this.status("idle"); });
  }
  /** Stops playback now; in-flight provider work retains its place until actual completion. */
  async stop() { this.epoch += 1; this.buffer = new SpeechSentenceBuffer(); await this.ctx.native.audio.stop(); }
}
