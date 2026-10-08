import { errorMessage, type BackgroundCtx, type PluginServiceReference } from "@yinfengwindy/shiori-sdk";
import type { ReplyBubbleController } from "../replyBubble";
import { cancelledResult, failedResult, roleNotShownError, skippedResult, succeededResult, type OutputResult, type ReplyOwner } from "../replyOutput";
import { SpeechSentenceBuffer } from "../voice/sentences";
import type { PetSpeechQueue, SpeechJob } from "../voice/speechQueue";
import { synthesizeSentence } from "../voice/synthesis";
import { readLiveReply, readLiveReplyIds, type LiveReply, type LiveReplyOutcome } from "./contract";
import { LiveOutcomeLedger } from "./outcomeLedger";
import { LiveRunRegistry } from "./runRegistry";

/** What the live presenter needs from the rest of the pet; injected so tests can fake it. */
export type LiveReplyPresenterDeps = {
  bubbles: Pick<ReplyBubbleController, "show" | "release" | "releaseAfter" | "clear">;
  speech: PetSpeechQueue;
  rpc: Pick<BackgroundCtx["rpc"], "services">;
  /** The synthesis service while pet speech is on, else null; read at each reply's turn. */
  ttsProvider(): PluginServiceReference | null;
  report(outcome: LiveReplyOutcome): Promise<unknown>;
  /** How long a reply that could not be heard stays readable. */
  fallbackMs?: number;
};

type Progress = { bubble: OutputResult; skipped: boolean; spoken: number };

/**
 * Presents live-source replies: bubble plus speech in the reply role's voice,
 * on the speech line shared with chat so the two never overlap.
 *
 * A reply's bubble appears when its turn on the line starts and is held while
 * it is spoken; unheard replies stay readable for a fallback duration. Live
 * speech never reads a session for mood. Every received reply is answered
 * with exactly one outcome (see `contract.ts`).
 */
export class LiveReplyPresenter {
  private roleId = "";
  private readonly runs = new LiveRunRegistry();
  private readonly ledger: LiveOutcomeLedger;

  constructor(private readonly deps: LiveReplyPresenterDeps) {
    this.ledger = new LiveOutcomeLedger(deps.report);
  }

  /** Entry for one `live.reply.show` payload; a malformed one is answered `failed`, then rethrown. */
  async receive(payload: Record<string, unknown>): Promise<void> {
    let reply: LiveReply;
    try {
      reply = readLiveReply(payload);
    } catch (error) {
      const ids = readLiveReplyIds(payload);
      const failed = failedResult(errorMessage(error));
      if (ids) await this.ledger.answer(this.ledger.track(ids), failed, failed);
      throw error;
    }
    if (this.ledger.closed) return;
    const entry = this.ledger.track({ reply_id: reply.replyId, run_id: reply.runId });
    const { bubble, speech } = await this.present(reply);
    await this.ledger.answer(entry, bubble, speech);
  }

  /** Cancels live replies (of one run when given) and rejects that run's later replies; chat is untouched. */
  async cancel(runId?: string): Promise<void> {
    this.runs.cancel(runId);
    this.deps.bubbles.clear("live", runId);
    await this.deps.speech.cancel({ source: "live", runId });
  }

  /** The pet's visible role; a change retires every live reply so none speaks for another role. */
  bind(roleId: string): Promise<void> {
    if (roleId === this.roleId) return Promise.resolve();
    this.roleId = roleId;
    const cancelling = this.cancel();
    this.runs.reset();
    return cancelling;
  }

  /** Plugin disable: answers every outstanding reply `cancelled` first, then never reports again. */
  async dispose(): Promise<void> {
    const cancelling = this.cancel();
    await this.ledger.close();
    await cancelling;
  }

  private async present(reply: LiveReply): Promise<{ bubble: OutputResult; speech: OutputResult }> {
    if (reply.roleId !== this.roleId) return { bubble: failedResult(roleNotShownError), speech: failedResult(roleNotShownError) };
    if (this.runs.isCancelled(reply.runId)) return { bubble: cancelledResult, speech: cancelledResult };
    this.runs.see(reply.runId);
    const owner: ReplyOwner = { source: "live", runId: reply.runId };
    const progress: Progress = { bubble: cancelledResult, skipped: false, spoken: 0 };
    const queued = await this.deps.speech.enqueue(owner, (job) => this.speak(reply, owner, job, progress));
    const speech = queued.status === "succeeded" && progress.skipped ? skippedResult : queued;
    // Heard in full or cancelled: the bubble ends with the speech. Unheard: keep it readable a while.
    if (speech.status === "cancelled" || (speech.status === "succeeded" && progress.spoken > 0)) this.deps.bubbles.release(owner);
    else if (speech.status !== "skipped") this.deps.bubbles.releaseAfter(owner, this.fallbackMs);
    return { bubble: progress.bubble, speech };
  }

  /** Runs at the reply's turn, so the role and speech availability are those of that moment. */
  private async speak(reply: LiveReply, owner: ReplyOwner, job: SpeechJob, progress: Progress) {
    const provider = this.deps.ttsProvider();
    const lifetime = provider ? { kind: "hold" as const } : { kind: "expire" as const, ms: this.fallbackMs };
    if (reply.roleId !== this.roleId || !this.deps.bubbles.show(owner, reply.roleId, reply.text, lifetime)) {
      progress.bubble = failedResult(roleNotShownError);
      throw new Error(roleNotShownError);
    }
    progress.bubble = succeededResult;
    if (!provider) { progress.skipped = true; return; }
    for (const sentence of new SpeechSentenceBuffer().push(reply.text, true)) {
      const audio = await synthesizeSentence(this.deps.rpc, provider, { text: sentence, roleId: reply.roleId, mood: "" });
      if (!job.active) return;
      await job.play(audio);
      progress.spoken += 1;
    }
  }

  private get fallbackMs() { return this.deps.fallbackMs ?? 5_000; }
}
