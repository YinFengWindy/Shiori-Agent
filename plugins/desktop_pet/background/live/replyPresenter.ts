import type { PluginServiceReference, TtsResult } from "@yinfengwindy/shiori-sdk";
import type { BubbleOwner, ReplyBubbleController } from "../replyBubble";
import { SpeechSentenceBuffer } from "../voice/sentences";
import type { PetSpeechQueue } from "../voice/speechQueue";
import type { LiveReply, LiveReplyOutcome, OutputResult } from "./contract";

/** What the live presenter needs from the rest of the pet; injected so tests can fake it. */
export type LiveReplyPresenterDeps = {
  bubbles: Pick<ReplyBubbleController, "show" | "release" | "clear">;
  speech: PetSpeechQueue;
  /** The chosen synthesis service, or null while pet speech is off. */
  ttsProvider(): PluginServiceReference | null;
  synthesize(provider: PluginServiceReference, payload: { text: string; role_id: string; mood: string }): Promise<TtsResult>;
  /** The role the pet currently shows; empty while hidden. */
  visibleRoleId(): string;
  report(outcome: LiveReplyOutcome): Promise<unknown>;
  /** How long a reply that could not be heard stays readable. */
  fallbackMs?: number;
};

const succeeded: OutputResult = { status: "succeeded" };
const cancelled: OutputResult = { status: "cancelled" };
const failed = (error: string): OutputResult => ({ status: "failed", error });

/**
 * Presents live-source replies: bubble plus speech in the reply role's voice,
 * through the speech line shared with chat so the two never overlap.
 *
 * A reply's bubble appears when its speech turn starts and is held until that
 * speech ends; without speech it expires after a fallback duration. Live
 * speech never reads a session for mood. Cancellation is live-only.
 */
export class LiveReplyPresenter {
  private disposed = false;
  private roleId = "";

  constructor(private readonly deps: LiveReplyPresenterDeps) {}

  /** Presents one reply and reports its bubble and speech outcome by reply id. */
  async show(reply: LiveReply): Promise<void> {
    if (this.disposed) return;
    const outcome = await this.present(reply);
    // A disabled pet's backend scope is gone too; there is no one to report to.
    if (!this.disposed) await this.deps.report(outcome);
  }

  /** Cancels live speech and bubbles (of one run when given); chat output is untouched. */
  async cancel(runId?: string): Promise<void> {
    this.deps.bubbles.clear("live", runId);
    await this.deps.speech.cancel("live", runId);
  }

  /** A changed visible role retires every live reply so none speaks in another role's place. */
  bind(roleId: string): Promise<void> {
    if (roleId === this.roleId) return Promise.resolve();
    this.roleId = roleId;
    return this.cancel();
  }

  /** Plugin disable: retire live work and never report again. */
  dispose(): Promise<void> {
    this.disposed = true;
    return this.cancel();
  }

  private async present(reply: LiveReply): Promise<LiveReplyOutcome> {
    const ids = { reply_id: reply.replyId, run_id: reply.runId };
    const owner: BubbleOwner = { source: "live", runId: reply.runId };
    const fallbackMs = this.deps.fallbackMs ?? 5_000;
    if (reply.roleId !== this.deps.visibleRoleId()) {
      const error = failed("桌宠未显示该回复的角色");
      return { ...ids, bubble: error, speech: error };
    }
    const provider = this.deps.ttsProvider();
    if (!provider) {
      const shown = this.deps.bubbles.show(owner, reply.roleId, reply.text, fallbackMs);
      return { ...ids, bubble: shown ? succeeded : failed("桌宠未显示该回复的角色"), speech: failed("桌宠语音未开启") };
    }
    let bubble = cancelled;
    let spoken = 0;
    const speech = await this.deps.speech.enqueue(owner, async (job) => {
      // Re-checked at its turn: the pet may have switched roles while this waited.
      if (reply.roleId !== this.deps.visibleRoleId() || !this.deps.bubbles.show(owner, reply.roleId, reply.text, null)) {
        bubble = failed("桌宠未显示该回复的角色");
        throw new Error("桌宠未显示该回复的角色");
      }
      bubble = succeeded;
      for (const sentence of new SpeechSentenceBuffer().push(reply.text, true)) {
        const audio = await this.deps.synthesize(provider, { text: sentence, role_id: reply.roleId, mood: "" });
        if (!job.active) return;
        await job.play(audio);
        spoken += 1;
      }
    });
    // Heard in full, or cancelled: the bubble ends with the speech. Otherwise keep it readable a while.
    const heard = speech.status === "succeeded" && spoken > 0;
    this.deps.bubbles.release(owner, heard || speech.status === "cancelled" ? null : fallbackMs);
    return { ...ids, bubble, speech };
  }
}
