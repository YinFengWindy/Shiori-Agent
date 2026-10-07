import { errorMessage } from "../errors";
import type { PluginRpcClient } from "../rpc";
import { SerialDraftQueue, type DraftSavePhase } from "../serialDraftQueue";

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

/** The quiet period of `usePrivateAutosave`, matching the host's plugin config autosave. */
export const privateAutosaveDebounceMs = 400;

function cloneDocument<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function documentsEqual<T>(a: T | null, b: T | null) {
  return a !== null && b !== null && JSON.stringify(a) === JSON.stringify(b);
}

/**
 * One scope's document lifecycle behind `usePrivateAutosave`: the load, the
 * edited draft, and the shared `SerialDraftQueue` that saves it. Once ended,
 * a session publishes nothing more, so late reads and saves of a previous
 * scope can never reach the next one; its operations are frozen at the last
 * render of its own scope, so a final flush still writes to that scope.
 */
export class PrivateAutosaveSession<T extends object> {
  /** Set when the user asked to read again: this session ends without submitting pending work. */
  reloading = false;
  private active = true;
  private draft: T | null = null;
  private saved: T | null = null;
  private readonly queue: SerialDraftQueue<T, T>;

  constructor(
    readonly client: PluginRpcClient,
    readonly identity: string,
    private operations: PrivateAutosaveOperations<T>,
    private readonly publish: (patch: Partial<PrivateAutosaveState<T>>) => void,
    debounceMs: number,
  ) {
    this.queue = new SerialDraftQueue<T, T>({
      debounceMs,
      isEqual: documentsEqual,
      clone: cloneDocument,
      attempt: async (value) => {
        try {
          return { ok: true, result: await this.operations.save(value) };
        } catch (cause) {
          // Any failed write keeps the draft and waits for an explicit retry.
          return { ok: false, resumesAutomatically: false, message: errorMessage(cause) };
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

  /** Follows the latest render's operations while this scope is still current. */
  setOperations(operations: PrivateAutosaveOperations<T>) {
    if (this.active) this.operations = operations;
  }

  /** Reads the document; a failure leaves no draft, so nothing can be saved over it. */
  load() {
    this.publish({ loading: true, loadError: "" });
    this.operations.load().then((value) => {
      if (!this.active) return;
      this.draft = cloneDocument(value);
      this.saved = cloneDocument(value);
      this.publish({ draft: this.draft, saved: this.saved, loading: false });
    }, (cause: unknown) => {
      if (this.active) this.publish({ loading: false, loadError: errorMessage(cause) });
    });
  }

  /** Replaces the draft; `save` schedules it after the quiet period or submits it at once. */
  edit(change: ((current: T) => T) | undefined, save: "none" | "debounced" | "now") {
    if (!this.active || this.draft === null) return;
    if (change) {
      const next = change(cloneDocument(this.draft));
      if (!documentsEqual(next, this.draft)) {
        this.draft = next;
        this.publish({ draft: next });
      }
    }
    if (save === "none") return;
    this.queue.enqueue(this.draft, this.saved ?? undefined);
    if (save === "now") this.queue.flush();
  }

  /** Resubmits the failed save, then any edit made since. */
  retry() {
    this.queue.retry();
  }

  /** Stops publishing; `flush` submits the last pending draft to this scope first. */
  end(flush: boolean) {
    this.active = false;
    if (flush) this.queue.flush();
  }
}
