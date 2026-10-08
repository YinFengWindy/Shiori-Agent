import { errorMessage, type BackgroundCtx, type PluginServiceReference } from "@yinfengwindy/shiori-sdk";
import type { ReplyOwner } from "../replyOutput";
import { SpeechSentenceBuffer } from "./sentences";
import { SentenceStream } from "./sentenceStream";
import type { PetSpeechQueue } from "./speechQueue";
import { synthesizeSentence } from "./synthesis";

const chatOwner: ReplyOwner = { source: "chat" };
type ReplyVoice = { provider: PluginServiceReference; roleId: string; mood: string };

/**
 * Chat-reply speech. One reply is one job on the shared speech line, opened at
 * its first sentence and finished by its final push, so nothing else speaks
 * between two sentences of the same reply.
 */
export class PetReplyAudio {
  private epoch = 0;
  private buffer = new SpeechSentenceBuffer();
  private text = "";
  private stream: SentenceStream | null = null;
  constructor(
    private readonly ctx: Pick<BackgroundCtx, "rpc">,
    private readonly speech: PetSpeechQueue,
    private readonly status: (status: "speaking_prepare" | "speaking" | "idle" | "error", message?: string) => void,
  ) {}
  /** Starts a new reply, abandoning whatever is left of the previous one. */
  begin() { this.reset(); return this.epoch; }
  push(text: string, final: boolean, provider: PluginServiceReference, roleId: string, mood: string) {
    if (!final) this.text += text;
    const sentences = this.buffer.push(final && !this.text ? text : final ? "" : text, final);
    if (!sentences.length && !final) return;
    const stream = this.stream ?? this.open({ provider, roleId, mood });
    stream.add(sentences, final);
    this.stream = final ? null : stream;
  }
  /**
   * Retires the current reply's state; its job ends at its next read. Stopping
   * audio already playing is the caller's choice of scope on the speech line.
   */
  reset() { this.epoch += 1; this.buffer = new SpeechSentenceBuffer(); this.text = ""; this.stream?.close(); this.stream = null; }

  private open(voice: ReplyVoice) {
    const epoch = this.epoch; const stream = new SentenceStream();
    void this.speech.enqueue(chatOwner, async (job) => {
      const current = () => epoch === this.epoch && job.active;
      try {
        for (let sentence = await stream.next(job.signal); sentence !== null && current(); sentence = await stream.next(job.signal)) {
          this.status("speaking_prepare");
          const result = await synthesizeSentence(this.ctx.rpc, voice.provider, { text: sentence, roleId: voice.roleId, mood: voice.mood });
          if (!current()) return;
          this.status("speaking");
          await job.play(result);
        }
        if (current()) this.status("idle");
      } catch (error) {
        // Retires the rest of this reply so later sentences do not speak past a failure.
        if (epoch === this.epoch) { this.reset(); this.status("error", errorMessage(error)); }
      }
    });
    return stream;
  }
}
