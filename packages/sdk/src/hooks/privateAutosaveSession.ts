import { errorMessage } from "../errors";
import type { PluginRpcClient } from "../rpc";
import { SerialDraftQueue, autosaveDebounceMs, type DraftSavePhase } from "../serialDraftQueue";

/** How `usePrivateAutosave` reads and writes its one plugin-owned document. */
export type PrivateAutosaveOperations<T> = {
  /** Reads the stored document; a rejection is shown as `loadError` and never replaced by a default. */
  load(): Promise<T>;
  /** Writes one complete document and resolves with what was stored; a rejection pauses autosave. */
  save(value: T): Promise<T>;
};

/** The rendered state of one autosave session (one client and document identity). */
export type PrivateAutosaveState<T> = {
  draft: T | null;
  saved: T | null;
  loading: boolean;
  loadError: string;
  savePhase: DraftSavePhase;
  saveError: string;
};

/** The state of a scope without a document (null identity) or before its session starts. */
export const emptyPrivateAutosaveState: PrivateAutosaveState<never> = {
  draft: null, saved: null, loading: false, loadError: "", savePhase: "idle", saveError: "",
};

/** The quiet period of `usePrivateAutosave`: the shared autosave quiet period. */
export const privateAutosaveDebounceMs = autosaveDebounceMs;

function cloneDocument<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function documentsEqual<T>(a: T | null, b: T | null) {
  return a !== null && b !== null && JSON.stringify(a) === JSON.stringify(b);
}

/**
 * One scope's document lifecycle behind `usePrivateAutosave`: the load, the
 * edited draft, and the shared `SerialDraftQueue` that saves it. Once ended
 * or discarded, a session publishes nothing more, so late reads and saves of
 * a previous scope can never reach the next one. Retiring freezes its
 * operations, so a final flush still writes to its own scope.
 */
export class PrivateAutosaveSession<T extends object> {
  private active = true;
  private discarded = false;
  private frozen: PrivateAutosaveOperations<T> | null = null;
  private saving = 0;
  private draft: T | null = null;
  private saved: T | null = null;
  private readonly queue: SerialDraftQueue<T, T>;

  constructor(
    readonly client: PluginRpcClient,
    readonly identity: string,
    /** The latest render's operations, read while this scope is current. */
    private readonly latest: { readonly current: PrivateAutosaveOperations<T> },
    private readonly publish: (patch: Partial<PrivateAutosaveState<T>>) => void,
    debounceMs: number,
  ) {
    this.queue = new SerialDraftQueue<T, T>({
      debounceMs,
      isEqual: documentsEqual,
      clone: cloneDocument,
      attempt: async (value) => {
        // A discarded session must never write, even if the queue still drains.
        if (this.discarded) return { ok: false, resumesAutomatically: false, message: "" };
        this.saving += 1;
        try {
          return { ok: true, result: await this.operations().save(value) };
        } catch (cause) {
          // Any failed write keeps the draft and waits for an explicit retry.
          return { ok: false, resumesAutomatically: false, message: errorMessage(cause) };
        } finally {
          this.saving -= 1;
        }
      },
      onApplied: (stored, submitted) => {
        if (!this.active) return;
        this.saved = cloneDocument(stored);
        // Adopt the stored form only when no newer edit replaced the submitted draft.
        if (documentsEqual(this.draft, submitted)) this.draft = cloneDocument(stored);
        this.publish({ draft: this.draft, saved: this.saved });
      },
      onStatus: (savePhase, saveError) => { if (this.active) this.publish({ savePhase, saveError }); },
    });
  }

  private operations() {
    return this.frozen ?? this.latest.current;
  }

  /** Whether a write is in flight; a re-read now could return the pre-save document. */
  get isSaving() {
    return this.saving > 0;
  }

  /** Reads the document; a failure leaves no draft, so nothing can be saved over it. */
  load() {
    this.publish({ loading: true, loadError: "" });
    this.operations().load().then((value) => {
      if (!this.active) return;
      this.draft = cloneDocument(value);
      this.saved = cloneDocument(value);
      this.publish({ draft: this.draft, saved: this.saved, loading: false });
    }, (cause: unknown) => {
      if (this.active) this.publish({ loading: false, loadError: errorMessage(cause) });
    });
  }

  /** Applies one edit to the loaded draft; nothing happens before a successful read. */
  private apply(change: (current: T) => T) {
    if (!this.active || this.draft === null) return;
    const next = change(cloneDocument(this.draft));
    if (!documentsEqual(next, this.draft)) {
      this.draft = next;
      this.publish({ draft: next });
    }
  }

  /** Edits the draft and saves the latest draft once edits pause. */
  update(change: (current: T) => T) {
    this.apply(change);
    if (this.active && this.draft) this.queue.enqueue(this.draft, this.saved ?? undefined);
  }

  /** Optionally edits the draft, then submits it without waiting for the quiet period. */
  commit(change?: (current: T) => T) {
    if (change) this.apply(change);
    if (!this.active || !this.draft) return;
    this.queue.enqueue(this.draft, this.saved ?? undefined);
    this.queue.flush();
  }

  /** Resubmits the failed save, then any edit made since. */
  retry() {
    if (this.active) this.queue.retry();
  }

  /**
   * Stops publishing and accepting edits, freezing the operations of this
   * scope; pending work waits for `end` or `discard`.
   */
  retire() {
    this.active = false;
    this.frozen ??= this.latest.current;
  }

  /** Leaves the scope: submits the last scheduled draft through its own operations. */
  end() {
    this.retire();
    if (!this.discarded) this.queue.flush();
  }

  /** Abandons the scope without writing: cancels the scheduled draft and any later save. */
  discard() {
    this.retire();
    this.discarded = true;
    this.queue.reset();
  }
}
