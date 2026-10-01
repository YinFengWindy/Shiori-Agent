/**
 * Status of one draft's save lifecycle. Owned here (not in a settings-domain
 * module) because `SerialDraftQueue` itself is domain-agnostic — plugin
 * config autosave uses it too — and `shared/` must not depend on any
 * specific domain module. `settings/settingsPageTypes.ts` re-exports this
 * under its historical name, `SettingsSavePhase`, for its own consumers.
 */
export type DraftSavePhase = "idle" | "saving" | "error" | "refresh-error" | "unknown";

/**
 * Outcome of one submission attempt against the backend. `resumesAutomatically`
 * names what it actually controls: whether the *next* edit the user makes is
 * enough to try again on its own (true), or whether nothing but an explicit
 * `retry()` (or a reload) will submit anything further (false). The
 * previous name, `retryable`, was backwards in practice — a `retryable:
 * false` outcome is exactly the one that can *only* move forward through
 * `retry()`; the `true` case never needs it at all.
 */
export type DraftAttemptOutcome<TResult> =
  | { ok: true; result: TResult }
  | { ok: false; message: string; detail?: string; phase?: "error" | "refresh-error" | "unknown"; resumesAutomatically: boolean };

export type SerialDraftQueueOptions<TDraft, TResult> = {
  /** Structural equality used to collapse no-op edits and detect obsolete queued drafts. */
  isEqual: (a: TDraft | null, b: TDraft | null) => boolean;
  /** Deep-clones a draft before it is queued or handed to a caller. */
  clone: (draft: TDraft) => TDraft;
  /** Submits one draft; `operationId` stays stable across retries of the same attempt. */
  attempt: (draft: TDraft, operationId: string) => Promise<DraftAttemptOutcome<TResult>>;
  /** Called once an attempt succeeds, with the backend result and the draft that produced it. */
  onApplied: (result: TResult, submitted: TDraft) => void;
  onStatus: (phase: DraftSavePhase, message: string, detail?: string) => void;
};

/**
 * Serializes draft submissions, coalesces superseded edits, and preserves a
 * failed attempt's identity so an explicit retry reuses the same operation
 * id. Extracted so the "call backend -> refresh local state -> surface
 * status" autosave pattern is implemented once and shared by every domain
 * that needs it (see AGENTS.md on not duplicating this flow), rather than
 * being copy-pasted per settings domain.
 */
export class SerialDraftQueue<TDraft, TResult> {
  private running = false;
  private failed = false;
  private paused = false;
  private queued: TDraft | null = null;
  private attempted: TDraft | null = null;
  private attemptOperationId: string | null = null;

  constructor(private readonly options: SerialDraftQueueOptions<TDraft, TResult>) {}

  /** Clears in-flight bookkeeping; callers reseed any external version state separately. */
  reset(): void {
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
      return;
    }
    if (this.options.isEqual(this.attempted, draft)) {
      this.queued = null;
      return;
    }
    this.queued = this.options.clone(draft);
    if (!this.running && !this.paused) void this.drain();
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
      this.options.onStatus("idle", "");
    } catch (error) {
      this.failed = true;
      this.paused = true;
      this.options.onStatus("unknown", "暂时无法确认保存结果，请重试以确认", error instanceof Error ? error.message : String(error));
    } finally {
      this.running = false;
      if (!this.paused && this.queued) void this.drain();
    }
  }
}
