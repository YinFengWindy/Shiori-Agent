import type { BackgroundCtx, PluginServiceReference, TtsResult } from "@yinfengwindy/shiori-sdk";
import { SpeechSentenceBuffer } from "./sentences";
import type { PetSpeechQueue, SpeechOwner } from "./speechQueue";

const chatOwner: SpeechOwner = { source: "chat" };

/** Chat-reply sentence buffering and cancellation; playback order belongs to the shared speech queue. */
export class PetReplyAudio {
  private epoch = 0;
  private buffer = new SpeechSentenceBuffer();
  private text = "";
  constructor(
    private readonly ctx: Pick<BackgroundCtx, "rpc">,
    private readonly speech: PetSpeechQueue,
    private readonly status: (status: "speaking_prepare" | "speaking" | "idle" | "error", message?: string) => void,
  ) {}
  begin() { this.epoch += 1; this.buffer = new SpeechSentenceBuffer(); this.text = ""; return this.epoch; }
  push(text: string, final: boolean, provider: PluginServiceReference, roleId: string, mood: string) {
    const epoch = this.epoch;
    if (!final) this.text += text;
    const sentences = this.buffer.push(final && !this.text ? text : final ? "" : text, final);
    for (const sentence of sentences) {
      void this.speech.enqueue(chatOwner, async (job) => {
        if (epoch !== this.epoch) return;
        try {
          this.status("speaking_prepare");
          const result = await this.ctx.rpc.services.call<TtsResult>(provider, "synthesize", { text: sentence, role_id: roleId, mood });
          if (epoch !== this.epoch || !job.active) return;
          this.status("speaking");
          await job.play(result);
        } catch (error) {
          // Retires the rest of this reply so later sentences do not speak past a failure.
          if (epoch === this.epoch) { this.epoch += 1; this.status("error", error instanceof Error ? error.message : String(error)); }
        }
      });
    }
    if (final) void this.speech.enqueue(chatOwner, async () => { if (epoch === this.epoch) this.status("idle"); });
  }
  /** Stops chat speech only; other sources on the shared queue keep speaking. */
  async stop() { this.epoch += 1; this.buffer = new SpeechSentenceBuffer(); await this.speech.cancel("chat"); }
}
