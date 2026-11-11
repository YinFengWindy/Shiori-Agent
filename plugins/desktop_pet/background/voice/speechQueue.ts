import { errorMessage, type BackgroundCtx, type NativeAudio } from "@yinfengwindy/shiori-sdk";
import { isRecord } from "../../provider/guards";
import type { PetPresentationState } from "../../provider";
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
  constructor(readonly owner: ReplyOwner, private readonly playAudio: (job: Job, audio: NativeAudio) => Promise<void>) {
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
    try { await this.playAudio(this, audio); } finally { this.playing = false; }
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
  private playback: { job: Job; requestId: string; playbackId: string | null } | null = null;

  constructor(private readonly audio: BackgroundCtx["native"]["audio"], private readonly output: (audio: PetPresentationState["audio"]) => void = () => {}) {}

  /** Correlates host observations with the exact queued play, including cancelled jobs. */
  observe(value: unknown): void {
    const current = this.playback;
    if (!current?.job.active || !isRecord(value) || value.request_id !== current.requestId || typeof value.playback_id !== "string" || !value.playback_id) return;
    if (value.phase === "started") {
      if (current.playbackId !== null) return;
      current.playbackId = value.playback_id;
      this.output({ playback_id: value.playback_id, amplitude: 0 });
    } else if (value.phase === "level" && value.playback_id === current.playbackId && typeof value.amplitude === "number" && Number.isFinite(value.amplitude) && value.amplitude >= 0 && value.amplitude <= 1) {
      this.output({ playback_id: value.playback_id, amplitude: value.amplitude });
    } else if (value.phase === "ended" && (current.playbackId === null || value.playback_id === current.playbackId)) {
      this.playback = null; this.output(null);
    }
  }

  private async play(job: Job, audio: NativeAudio): Promise<void> {
    const current = { job, requestId: crypto.randomUUID(), playbackId: null };
    this.playback = current;
    this.output(null);
    try { await this.audio.play({ ...audio, request_id: current.requestId }); }
    finally { if (this.playback === current) { this.playback = null; this.output(null); } }
  }

  /** Appends one job; resolves with its outcome (never `skipped`) once it has run or been dropped. */
  enqueue(owner: ReplyOwner, work: (job: SpeechJob) => Promise<void>): Promise<OutputResult> {
    const job = new Job(owner, (job, audio) => this.play(job, audio));
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
    if (this.playback && inScope(this.playback.job)) { this.playback = null; this.output(null); }
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
