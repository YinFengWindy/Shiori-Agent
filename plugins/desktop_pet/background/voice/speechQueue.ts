import { errorMessage, type BackgroundCtx, type NativeAudio } from "@yinfengwindy/shiori-sdk";
import { cancelledResult, failedResult, succeededResult, type OutputResult, type PetReplySource, type ReplyOwner } from "../replyOutput";

/** The handle a running job uses to learn whether it is still wanted and to play audio. */
export type SpeechJob = {
  readonly owner: ReplyOwner;
  /** False once the job was cancelled; late synthesis must then not play. */
  readonly active: boolean;
  /** Aborted on cancellation, so a job waiting for more input wakes up and ends. */
  readonly signal: AbortSignal;
  /** Plays through the host player unless the job was cancelled first. */
  play(audio: NativeAudio): Promise<void>;
};

/** Selects which jobs a cancellation reaches; omitted, it reaches every source. */
export type SpeechScope = { source: PetReplySource; runId?: string };

class Job implements SpeechJob {
  playing = false;
  started = false;
  /** Resolves once: when the job finishes running, or at cancellation if it never started. */
  readonly outcome: Promise<OutputResult>;
  readonly settle: (result: OutputResult) => void;
  private readonly abort = new AbortController();
  constructor(readonly owner: ReplyOwner, private readonly audio: BackgroundCtx["native"]["audio"]) {
    let settle: (result: OutputResult) => void = () => {};
    this.outcome = new Promise((resolve) => { settle = resolve; });
    this.settle = settle;
  }

  get active() { return !this.abort.signal.aborted; }
  get signal() { return this.abort.signal; }
  cancel() { this.abort.abort(); }

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
 * The host player's `stop()` is global, so a scoped cancellation only calls it
 * when the job currently playing is in scope; other sources keep speaking. A
 * cancelled job whose provider call is still in flight keeps its place until
 * that call returns, so a newer job never races an unfinished inference; a
 * cancelled job that never started settles at once, without waiting for the
 * jobs ahead of it.
 */
export class PetSpeechQueue {
  private tail = Promise.resolve();
  private readonly jobs = new Set<Job>();
  private current: Job | null = null;

  constructor(private readonly audio: BackgroundCtx["native"]["audio"]) {}

  /** Appends one job; resolves with its outcome (never `skipped`) once it has run or been dropped. */
  enqueue(owner: ReplyOwner, work: (job: SpeechJob) => Promise<void>): Promise<OutputResult> {
    const job = new Job(owner, this.audio);
    this.jobs.add(job);
    this.tail = this.tail.then(() => this.execute(job, work));
    return job.outcome;
  }

  /** Cancels queued and running jobs in `scope` (every job when omitted), leaving others untouched. */
  async cancel(scope?: SpeechScope) {
    const inScope = (job: Job) => !scope || (job.owner.source === scope.source && (scope.runId === undefined || job.owner.runId === scope.runId));
    const current = this.current;
    const stopPlayback = Boolean(current && inScope(current) && current.playing);
    for (const job of this.jobs) {
      if (!inScope(job)) continue;
      job.cancel();
      if (!job.started) { job.settle(cancelledResult); this.jobs.delete(job); }
    }
    if (stopPlayback) await this.audio.stop();
  }

  private async execute(job: Job, work: (job: SpeechJob) => Promise<void>): Promise<void> {
    // Cancelled before its turn: already settled by `cancel`.
    if (!job.active) return;
    job.started = true;
    this.current = job;
    try {
      await work(job);
      job.settle(job.active ? succeededResult : cancelledResult);
    } catch (error) {
      // A stop interrupting playback is the cancellation itself, not a failure.
      job.settle(job.active ? failedResult(errorMessage(error)) : cancelledResult);
    } finally {
      this.current = null;
      this.jobs.delete(job);
    }
  }
}
