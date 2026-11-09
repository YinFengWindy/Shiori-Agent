import { errorMessage, type BackgroundCtx, type PluginServiceReference, type TtsResult } from "@yinfengwindy/shiori-sdk";
import type { ReplyOwner } from "../replyOutput";
import { SpeechSentenceBuffer } from "./sentences";
import { SentenceStream } from "./sentenceStream";
import type { PetSpeechQueue } from "./speechQueue";
import { synthesizeSentence } from "./synthesis";

const chatOwner: ReplyOwner = { source: "chat" };
type ReplyVoice = { provider: PluginServiceReference; roleId: string; mood: string };
type PreparedSpeech = { kind: "audio"; audio: TtsResult } | { kind: "end" } | { kind: "failed"; error: unknown };

/**
 * How long a reply being spoken may go without any delta before it gives up
 * the shared speech line. Every turn ends with `chat.done`, `chat.error` or
 * `chat.cancelled`, so this is only a fallback for a reply that stalls (e.g. a
 * long tool call) and keeps queued live replies from going stale. 15 s is far
 * above the gap between streamed deltas. A reply resuming after it is not
 * dropped: its later sentences open a new job at the back of the line, so
 * they never cut into a live reply mid-job.
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
  /** The reply's speech failed; its remaining deltas are not spoken. */
  private ended = false;
  /** The reply has opened at least one job; each job reports idle when it ends. */
  private opened = false;
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
    if (!sentences.length && !this.stream) {
      // Final with nothing left to say (e.g. after an idle timeout): no empty
      // job. Only a reply that never spoke still has to settle to idle here.
      if (!this.opened) this.status("idle");
      return;
    }
    const stream = this.stream ?? this.open({ provider, roleId, mood });
    stream.add(sentences, final);
    this.stream = final ? null : stream;
    this.armIdle();
  }
  /**
   * Retires the current reply's state; its job ends at its next read. Stopping
   * audio already playing is the caller's choice of scope on the speech line.
   */
  reset() { this.epoch += 1; this.buffer = new SpeechSentenceBuffer(); this.text = ""; this.opened = false; this.stream?.close(); this.stream = null; this.armIdle(); }

  /** Restarts the stall timer while a reply holds the speech line; any delta counts as activity. */
  private armIdle() {
    if (this.idleTimer !== null) clearTimeout(this.idleTimer);
    this.idleTimer = null;
    const stream = this.stream;
    if (!stream) return;
    this.idleTimer = setTimeout(() => {
      this.idleTimer = null;
      // Finished like a final push: buffered sentences still speak, and a later
      // sentence of this reply re-queues as a new job behind whatever waited.
      stream.add([], true);
      this.stream = null;
    }, chatReplyIdleMs);
    this.idleTimer.unref?.();
  }

  private open(voice: ReplyVoice) {
    const epoch = this.epoch; const stream = new SentenceStream(); this.opened = true;
    void this.speech.enqueue(chatOwner, async (job) => {
      const current = () => epoch === this.epoch && job.active;
      const prepare = async (): Promise<PreparedSpeech> => {
        try {
          const sentence = await stream.next(job.signal);
          if (sentence === null || !current()) return { kind: "end" };
          const audio = await synthesizeSentence(this.ctx.rpc, voice.provider, { text: sentence, roleId: voice.roleId, mood: voice.mood });
          return { kind: "audio", audio };
        } catch (error) {
          // Capture prefetch failures immediately, even while the current clip plays.
          return { kind: "failed", error };
        }
      };
      let pending = prepare();
      try {
        while (current()) {
          this.status("speaking_prepare");
          const result = await pending;
          if (!current()) return;
          if (result.kind === "end") break;
          if (result.kind === "failed") throw result.error;
          this.status("speaking");
          const playing = job.play(result.audio);
          // Only one segment ahead: synthesis overlaps playback, never another synthesis.
          pending = prepare();
          await playing;
        }
        if (current()) this.status("idle");
      } catch (error) {
        // Retires the rest of this reply so later sentences do not speak past a failure.
        if (current()) { this.reset(); this.ended = true; this.status("error", errorMessage(error)); }
      } finally {
        // Wake a pending sentence read on failure, and keep the queue occupied until
        // any already accepted provider call settles, including cancelled prefetch.
        stream.close();
        await pending;
      }
    });
    return stream;
  }
}
