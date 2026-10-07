/**
 * Status of one draft's save lifecycle, shared by the host settings pages,
 * the schema plugin config page and `usePrivateAutosave`, so every autosaved
 * page drives the same 「已保存」 indicator (`host.ui.SettingsSavedStatus`).
 * The host's `settings/settingsPageTypes.ts` re-exports it under its
 * historical name, `SettingsSavePhase`.
 */
export type DraftSavePhase = "idle" | "saving" | "error" | "refresh-error" | "unknown";

/**
 * Outcome of one submission attempt against the backend. On failure,
 * `resumesAutomatically` says whether the next edit submits again on its own
 * (true), or whether nothing further is submitted until an explicit `retry()`
 * or a reload (false).
 */
export type DraftAttemptOutcome<TResult> =
  | { ok: true; result: TResult }
  | { ok: false; message: string; detail?: string; phase?: "error" | "refresh-error" | "unknown"; resumesAutomatically: boolean };

/** Behaviour of one `SerialDraftQueue`: equality, cloning, the backend attempt and its callbacks. */
export type SerialDraftQueueOptions<TDraft, TResult> = {
  /** Quiet period for merging edits; omitted/zero preserves immediate submission. */
  debounceMs?: number;
  /** Structural equality used to collapse no-op edits and detect obsolete queued drafts. */
  isEqual: (a: TDraft | null, b: TDraft | null) => boolean;
  /** Deep-clones a draft before it is queued or handed to a caller. */
  clone: (draft: TDraft) => TDraft;
  /** Submits one draft; `operationId` stays stable across retries of the same attempt. */
  attempt: (draft: TDraft, operationId: string) => Promise<DraftAttemptOutcome<TResult>>;
  /** Called once an attempt succeeds, with the backend result and the draft that produced it. */
  onApplied: (result: TResult, submitted: TDraft) => void;
  /** Reports every phase change, with the failure message and folded detail when there is one. */
  onStatus: (phase: DraftSavePhase, message: string, detail?: string) => void;
};

/**
 * Serializes draft submissions, coalesces superseded edits, and preserves a
 * failed attempt's identity so an explicit retry reuses the same operation
 * id. Extracted so the "call backend -> refresh local state -> surface
 * status" autosave pattern is implemented once and shared by every domain
 * that needs it (see AGENTS.md on not duplicating this flow), rather than
 * being copy-pasted per settings domain. Lives in the SDK so the host's
 * settings autosave and plugins' `usePrivateAutosave` share one queue.
 */
export class SerialDraftQueue<TDraft, TResult> {
  private timer: ReturnType<typeof setTimeout> | undefined;
  private running = false;
  private failed = false;
  private paused = false;
  private queued: TDraft | null = null;
  private attempted: TDraft | null = null;
  private attemptOperationId: string | null = null;

  constructor(private readonly options: SerialDraftQueueOptions<TDraft, TResult>) {}

  /** Reports work whose draft or retry identity must survive an external refresh. */
  get hasPendingWork() {
    return this.running || this.failed || this.queued !== null;
  }

  /** Clears in-flight bookkeeping; callers reseed any external version state separately. */
  reset(): void {
    this.cancelTimer();
    this.failed = false;
    this.paused = false;
    this.queued = null;
    this.attempted = null;
    this.attemptOperationId = null;
  }

  /** Schedules the newest draft; failed requests pause subsequent writes until retry or reload. */
  enqueue(draft: TDraft, persisted?: TDraft): void {
    if (!this.running && !this.failed && this.options.isEqual(persisted ?? null, draft)) {
      this.queued = null;
      this.cancelTimer();
      this.options.onStatus("idle", "");
      return;
    }
    if ((this.running || this.failed) && this.options.isEqual(this.attempted, draft)) {
      this.queued = null;
      this.cancelTimer();
      return;
    }
    if (this.options.isEqual(this.queued, draft)) return;
    this.queued = this.options.clone(draft);
    this.cancelTimer();
    const delay = this.options.debounceMs ?? 0;
    if (delay > 0) {
      this.timer = setTimeout(() => { this.timer = undefined; this.submitReady(); }, delay);
      if (!this.paused && !this.running) this.options.onStatus("saving", "");
    } else this.submitReady();
  }

  /** Submits the last pending draft when leaving its editor, preserving failure pauses. */
  flush(): void {
    this.cancelTimer();
    this.submitReady();
  }

  private cancelTimer() {
    if (this.timer !== undefined) clearTimeout(this.timer);
    this.timer = undefined;
  }

  private submitReady() {
    if (!this.running && !this.paused && this.timer === undefined && this.queued) void this.drain();
  }

  /** Retries the exact failed transaction before processing any newer queued edits. */
  retry(): void {
    if (this.running || !this.failed || !this.attempted) return;
    this.failed = false;
    void this.drain(this.attempted);
  }

  private async drain(retry?: TDraft) {
    const draft = retry ?? this.queued;
    if (!draft) return;
    if (!retry) {
      this.queued = null;
      this.attempted = this.options.clone(draft);
      this.attemptOperationId = crypto.randomUUID();
    }
    this.running = true;
    this.failed = false;
    this.options.onStatus("saving", "");
    try {
      const outcome = await this.options.attempt(draft, this.attemptOperationId!);
      if (!outcome.ok) {
        this.failed = true;
        this.paused = !outcome.resumesAutomatically;
        this.options.onStatus(outcome.phase ?? "error", outcome.message, outcome.detail);
        return;
      }
      this.paused = false;
      this.options.onApplied(outcome.result, draft);
      // A newer draft is still unsaved even if this transaction succeeded.
      if (!this.queued) this.options.onStatus("idle", "");
    } catch (error) {
      this.failed = true;
      this.paused = true;
      this.options.onStatus("unknown", "暂时无法确认保存结果，请重试以确认", error instanceof Error ? error.message : String(error));
    } finally {
      this.running = false;
      this.submitReady();
    }
  }
}
