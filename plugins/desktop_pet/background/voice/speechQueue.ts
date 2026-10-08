import type { BackgroundCtx, NativeAudio } from "@yinfengwindy/shiori-sdk";

/** Which producer a spoken reply belongs to; cancellation never crosses sources. */
export type PetReplySource = "chat" | "live";

/** Identifies the producer of one speech job; `runId` narrows live cancellation to one run. */
export type SpeechOwner = { source: PetReplySource; runId?: string };

/** How one job ended: only a job that ran to completion while still wanted succeeded. */
export type SpeechOutcome =
  | { status: "succeeded" }
  | { status: "cancelled" }
  | { status: "failed"; error: string };

/** The handle a running job uses to learn whether it is still wanted and to play audio. */
export type SpeechJob = {
  readonly owner: SpeechOwner;
  /** False once the job's owner cancelled it; late synthesis must then not play. */
  readonly active: boolean;
  /** Plays through the host player unless the job was cancelled first. */
  play(audio: NativeAudio): Promise<void>;
};

class Job implements SpeechJob {
  active = true;
  playing = false;
  constructor(readonly owner: SpeechOwner, private readonly audio: BackgroundCtx["native"]["audio"]) {}

  async play(audio: NativeAudio) {
    if (!this.active) return;
    this.playing = true;
    try { await this.audio.play(audio); } finally { this.playing = false; }
  }
}

/**
 * The pet's single local speech line: every source's synthesis and playback
 * runs here one job at a time, so chat and live speech never overlap.
 *
 * The host player's `stop()` is global, so cancellation only calls it when the
 * job currently playing belongs to the cancelled owner; otherwise other
 * sources keep speaking. A cancelled job whose provider call is still in
 * flight keeps its place until that call actually returns, so a newer job never
 * races an unfinished inference.
 */
export class PetSpeechQueue {
  private tail = Promise.resolve();
  private readonly jobs = new Set<Job>();
  private current: Job | null = null;

  constructor(private readonly audio: BackgroundCtx["native"]["audio"]) {}

  /** Appends one job; resolves with its outcome once it has run or been skipped. */
  enqueue(owner: SpeechOwner, work: (job: SpeechJob) => Promise<void>): Promise<SpeechOutcome> {
    const job = new Job(owner, this.audio);
    this.jobs.add(job);
    const run = this.tail.then(() => this.execute(job, work));
    this.tail = run.then(() => undefined);
    return run;
  }

  /** Cancels queued and running jobs of one source (optionally one run), leaving others untouched. */
  async cancel(source: PetReplySource, runId?: string) {
    const matches = (job: Job) => job.owner.source === source && (runId === undefined || job.owner.runId === runId);
    for (const job of this.jobs) if (matches(job)) job.active = false;
    const current = this.current;
    if (current && matches(current) && current.playing) await this.audio.stop();
  }

  private async execute(job: Job, work: (job: SpeechJob) => Promise<void>): Promise<SpeechOutcome> {
    if (!job.active) { this.jobs.delete(job); return { status: "cancelled" }; }
    this.current = job;
    try {
      await work(job);
      return job.active ? { status: "succeeded" } : { status: "cancelled" };
    } catch (error) {
      // A stop interrupting playback is the cancellation itself, not a failure.
      return job.active ? { status: "failed", error: error instanceof Error ? error.message : String(error) } : { status: "cancelled" };
    } finally {
      this.current = null;
      this.jobs.delete(job);
    }
  }
}
