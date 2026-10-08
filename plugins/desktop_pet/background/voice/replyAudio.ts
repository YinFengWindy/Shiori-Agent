import { errorMessage, type BackgroundCtx, type PluginServiceReference } from "@yinfengwindy/shiori-sdk";
import type { ReplyOwner } from "../replyOutput";
import { SpeechSentenceBuffer } from "./sentences";
import { SentenceStream } from "./sentenceStream";
import type { PetSpeechQueue } from "./speechQueue";
import { synthesizeSentence } from "./synthesis";

const chatOwner: ReplyOwner = { source: "chat" };
type ReplyVoice = { provider: PluginServiceReference; roleId: string; mood: string };

/**
 * How long a reply being spoken may go without any delta before its speech is
 * treated as finished. The host emits neither `chat.done` nor `chat.error`
 * when a turn is cancelled elsewhere, so without this a stalled reply would
 * hold the shared speech line forever. 15 s is far above the gap between
 * streamed deltas yet short enough that queued live replies are not stale by
 * the time they speak; a reply resuming after it (e.g. a long tool call) goes
 * unspoken rather than blocking every other source.
 */
export const chatReplyIdleMs = 15_000;

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
  /** The reply's speech ended early (failure or stall); its remaining deltas are not spoken. */
  private ended = false;
  private idleTimer: ReturnType<typeof setTimeout> | null = null;
  constructor(
    private readonly ctx: Pick<BackgroundCtx, "rpc">,
    private readonly speech: PetSpeechQueue,
    private readonly status: (status: "speaking_prepare" | "speaking" | "idle" | "error", message?: string) => void,
  ) {}
  /** Starts a new reply, abandoning whatever is left of the previous one. */
  begin() { this.reset(); this.ended = false; return this.epoch; }
  push(text: string, final: boolean, provider: PluginServiceReference, roleId: string, mood: string) {
    if (this.ended) return;
    if (!final) this.text += text;
    const sentences = this.buffer.push(final && !this.text ? text : final ? "" : text, final);
    if (!sentences.length && !final) { this.armIdle(); return; }
    const stream = this.stream ?? this.open({ provider, roleId, mood });
    stream.add(sentences, final);
    this.stream = final ? null : stream;
    this.armIdle();
  }
  /**
   * Retires the current reply's state; its job ends at its next read. Stopping
   * audio already playing is the caller's choice of scope on the speech line.
   */
  reset() { this.epoch += 1; this.buffer = new SpeechSentenceBuffer(); this.text = ""; this.stream?.close(); this.stream = null; this.armIdle(); }

  /** Restarts the stall timer while a reply holds the speech line; any delta counts as activity. */
  private armIdle() {
    if (this.idleTimer !== null) clearTimeout(this.idleTimer);
    this.idleTimer = null;
    const stream = this.stream;
    if (!stream) return;
    this.idleTimer = setTimeout(() => {
      this.idleTimer = null;
      // Finished like a final push: buffered sentences still speak, later deltas do not.
      stream.add([], true);
      this.stream = null; this.ended = true;
    }, chatReplyIdleMs);
    this.idleTimer.unref?.();
  }

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
        if (epoch === this.epoch) { this.reset(); this.ended = true; this.status("error", errorMessage(error)); }
      }
    });
    return stream;
  }
}
