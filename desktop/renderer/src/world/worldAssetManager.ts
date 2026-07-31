const controlledLocalAssetPattern = /^shiori-asset:\/\/local\/[^/?#]+$/;

export type WorldAssetKind = "background" | "character" | "cg" | "avatar";

/** One renderer-safe local asset addressable by presentation cues. */
export type WorldAssetManifestEntry = {
  id: string;
  url: string;
  kind: WorldAssetKind;
  estimatedBytes?: number;
  fallbackIds?: string[];
};

export type LoadedWorldAsset<TAsset> = {
  asset: TAsset;
  sizeBytes?: number;
};

export type WorldAssetLoader<TAsset> = (
  entry: WorldAssetManifestEntry,
  options: { signal: AbortSignal },
) => Promise<LoadedWorldAsset<TAsset>>;

type ManagedAsset<TAsset> = {
  entry: WorldAssetManifestEntry;
  asset: TAsset | null;
  load: Promise<TAsset> | null;
  loadController: AbortController | null;
  refCount: number;
  lastAccess: number;
  sizeBytes: number;
};

export type WorldAssetManagerOptions<TAsset> = {
  loader: WorldAssetLoader<TAsset>;
  destroy: (asset: TAsset) => void;
  softBudgetBytes?: number;
  maxEntries?: number;
  timeoutMs?: number;
};

export class WorldAssetTimeoutError extends Error {
  constructor(readonly assetId: string, timeoutMs: number) {
    super(`world asset ${assetId} timed out after ${timeoutMs}ms`);
    this.name = "WorldAssetTimeoutError";
  }
}

/** Owns world-stage asset loading, retention, eviction, cancellation, and disposal. */
export class WorldAssetManager<TAsset> {
  readonly #assets = new Map<string, ManagedAsset<TAsset>>();
  readonly #loader: WorldAssetLoader<TAsset>;
  readonly #destroy: (asset: TAsset) => void;
  readonly #softBudgetBytes: number;
  readonly #maxEntries: number;
  readonly #timeoutMs: number;
  #accessSequence = 0;
  #disposed = false;

  constructor(options: WorldAssetManagerOptions<TAsset>) {
    this.#loader = options.loader;
    this.#destroy = options.destroy;
    this.#softBudgetBytes = options.softBudgetBytes ?? 256 * 1024 * 1024;
    this.#maxEntries = options.maxEntries ?? 64;
    this.#timeoutMs = options.timeoutMs ?? 10_000;
  }

  /** Registers validated opaque local URLs without starting I/O. */
  registerManifest(entries: readonly WorldAssetManifestEntry[]): void {
    this.#assertActive();
    for (const entry of entries) {
      if (!entry.id.trim()) throw new Error("world asset id is required");
      if (!controlledLocalAssetPattern.test(entry.url)) {
        throw new Error(`world asset ${entry.id} must use the controlled local asset transport`);
      }
      const existing = this.#assets.get(entry.id);
      if (existing && existing.entry.url !== entry.url) {
        if (existing.refCount > 0 || existing.load) {
          throw new Error(`cannot replace active world asset ${entry.id}`);
        }
        this.#evict(existing);
        existing.entry = { ...entry, fallbackIds: entry.fallbackIds ? [...entry.fallbackIds] : undefined };
        existing.lastAccess = this.#touch();
        existing.sizeBytes = Math.max(0, entry.estimatedBytes ?? 0);
      }
      if (!this.#assets.has(entry.id)) {
        this.#assets.set(entry.id, {
          entry: { ...entry, fallbackIds: entry.fallbackIds ? [...entry.fallbackIds] : undefined },
          asset: null,
          load: null,
          loadController: null,
          refCount: 0,
          lastAccess: this.#touch(),
          sizeBytes: Math.max(0, entry.estimatedBytes ?? 0),
        });
      }
    }
  }

  /** Preloads assets without retaining them as part of the current stage. */
  async preload(ids: readonly string[], options: { signal?: AbortSignal; timeoutMs?: number } = {}) {
    const assets = await Promise.all(ids.map(async (id) => [id, await this.#load(id, options)] as const));
    this.#enforceBudget();
    return new Map(assets);
  }

  /** Loads and retains one asset until a matching release. */
  async acquire(id: string, options: { signal?: AbortSignal; timeoutMs?: number } = {}): Promise<TAsset> {
    const asset = await this.#load(id, options);
    const managed = this.#required(id);
    managed.refCount += 1;
    managed.lastAccess = this.#touch();
    return asset;
  }

  /** Releases one active reference and evicts unused LRU entries over budget. */
  release(id: string): void {
    this.#assertActive();
    const managed = this.#required(id);
    if (managed.refCount === 0) throw new Error(`world asset ${id} has no active reference`);
    managed.refCount -= 1;
    managed.lastAccess = this.#touch();
    this.#enforceBudget();
  }

  /** Returns observable lifecycle data for diagnostics and leak tests. */
  stats() {
    const ready = [...this.#assets.values()].filter((item) => item.asset !== null);
    return {
      manifestEntries: this.#assets.size,
      readyEntries: ready.length,
      pendingEntries: [...this.#assets.values()].filter((item) => item.load !== null).length,
      retainedEntries: ready.filter((item) => item.refCount > 0).length,
      totalBytes: ready.reduce((total, item) => total + item.sizeBytes, 0),
    };
  }

  /** Cancels pending loads and destroys every owned asset exactly once. */
  dispose(): void {
    if (this.#disposed) return;
    this.#disposed = true;
    for (const managed of this.#assets.values()) {
      managed.loadController?.abort();
      if (managed.asset !== null) this.#destroy(managed.asset);
      managed.asset = null;
      managed.load = null;
      managed.loadController = null;
      managed.refCount = 0;
    }
    this.#assets.clear();
  }

  async #load(id: string, options: { signal?: AbortSignal; timeoutMs?: number }): Promise<TAsset> {
    this.#assertActive();
    const managed = this.#required(id);
    managed.lastAccess = this.#touch();
    if (managed.asset !== null) return managed.asset;
    if (!managed.load) {
      const controller = new AbortController();
      const timeoutMs = options.timeoutMs ?? this.#timeoutMs;
      let timedOut = false;
      const timeout = setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, timeoutMs);
      managed.loadController = controller;
      managed.load = this.#loader(managed.entry, { signal: controller.signal })
        .then((loaded) => {
          if (this.#disposed) {
            this.#destroy(loaded.asset);
            throw new Error("world asset manager is disposed");
          }
          managed.asset = loaded.asset;
          managed.sizeBytes = Math.max(0, loaded.sizeBytes ?? managed.entry.estimatedBytes ?? 0);
          managed.lastAccess = this.#touch();
          return loaded.asset;
        })
        .catch((error) => {
          if (timedOut) throw new WorldAssetTimeoutError(id, timeoutMs);
          throw error;
        })
        .finally(() => {
          clearTimeout(timeout);
          managed.load = null;
          managed.loadController = null;
        });
    }
    return await this.#waitForCaller(managed.load, options.signal);
  }

  async #waitForCaller(load: Promise<TAsset>, signal?: AbortSignal): Promise<TAsset> {
    if (!signal) return await load;
    if (signal.aborted) throw signal.reason ?? new DOMException("Aborted", "AbortError");
    return await new Promise<TAsset>((resolve, reject) => {
      const abort = () => reject(signal.reason ?? new DOMException("Aborted", "AbortError"));
      signal.addEventListener("abort", abort, { once: true });
      void load.then(resolve, reject).finally(() => signal.removeEventListener("abort", abort));
    });
  }

  #enforceBudget(): void {
    const unused = [...this.#assets.values()]
      .filter((item) => item.asset !== null && item.refCount === 0)
      .sort((left, right) => left.lastAccess - right.lastAccess);
    let readyCount = [...this.#assets.values()].filter((item) => item.asset !== null).length;
    let totalBytes = [...this.#assets.values()].reduce(
      (total, item) => total + (item.asset === null ? 0 : item.sizeBytes),
      0,
    );
    for (const managed of unused) {
      if (readyCount <= this.#maxEntries && totalBytes <= this.#softBudgetBytes) break;
      totalBytes -= managed.sizeBytes;
      readyCount -= 1;
      this.#evict(managed);
    }
  }

  #evict(managed: ManagedAsset<TAsset>): void {
    if (managed.asset !== null) this.#destroy(managed.asset);
    managed.asset = null;
    managed.sizeBytes = Math.max(0, managed.entry.estimatedBytes ?? 0);
  }

  #required(id: string): ManagedAsset<TAsset> {
    const managed = this.#assets.get(id);
    if (!managed) throw new Error(`unknown world asset ${id}`);
    return managed;
  }

  #assertActive(): void {
    if (this.#disposed) throw new Error("world asset manager is disposed");
  }

  #touch(): number {
    this.#accessSequence += 1;
    return this.#accessSequence;
  }
}
