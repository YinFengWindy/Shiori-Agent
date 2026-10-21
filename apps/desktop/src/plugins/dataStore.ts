import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { join } from "node:path";

/** File-name-safe plugin ids; anything else could escape the store directory. */
const safePluginId = /^[A-Za-z0-9_-]+$/;

export type PluginDataStoreOptions = {
  /** Directory holding one `<pluginId>.json` per plugin. */
  directory: string;
  /** Reports a failed read or write; the store itself never throws at callers. */
  onError?: (pluginId: string, operation: "read" | "write", error: unknown) => void;
};

export class PluginDataStoreError extends Error {}

/**
 * Persists one JSON blob per plugin on the plugin's behalf.
 *
 * A plugin's always-resident `app.background` code runs in a renderer (see
 * `pluginHost/window.ts`), so it has no filesystem of its own — but plenty of
 * plugins have state that must outlive a restart and does not belong in their
 * user-facing config (`plugin.config.*`): the desktop pet's remembered window
 * position per role and display is the first case, and it is runtime state, not
 * something to show in a settings form.
 *
 * The shape of the blob is entirely the plugin's business; this class only
 * knows it is JSON.
 */
export class PluginDataStore {
  private readonly snapshots = new Map<string, unknown>();
  private readonly listeners = new Set<(pluginId: string, value: unknown) => void>();
  /** Per-plugin write chain, so two concurrent writes cannot interleave their renames. */
  private readonly writeChains = new Map<string, Promise<void>>();

  constructor(private readonly options: PluginDataStoreOptions) {}

  /**
   * Reads a plugin's stored value.
   *
   * A missing or unparseable file reads as `null` rather than throwing: an
   * absent file is the ordinary state of a plugin that has never written, and
   * a corrupt one is not something a plugin can act on any better than by
   * starting from its own defaults.
   */
  async read(pluginId: string): Promise<unknown> {
    const stored = await this.readJson(pluginId, this.pathFor(pluginId));
    const value = stored.present ? stored.value : null;
    this.snapshots.set(pluginId, value);
    return value;
  }

  /** Replaces a plugin's stored value and notifies `onChanged` observers. */
  async write(pluginId: string, value: unknown): Promise<void> {
    const path = this.pathFor(pluginId);
    const serialized = `${JSON.stringify(value, null, 2)}\n`;
    const chain = (this.writeChains.get(pluginId) ?? Promise.resolve()).then(async () => {
      await mkdir(this.options.directory, { recursive: true });
      const temporaryPath = `${path}.tmp`;
      await writeFile(temporaryPath, serialized, "utf-8");
      // Rename, not a second `writeFile`: a crash between two writes leaves a
      // truncated file that reads as corrupt, while a rename is atomic on both
      // Windows and POSIX, so the file is either wholly old or wholly new.
      await rename(temporaryPath, path);
    });
    this.writeChains.set(pluginId, chain.catch(() => undefined));
    await chain;
    this.snapshots.set(pluginId, value);
    for (const listener of this.listeners) listener(pluginId, value);
  }

  /**
   * The last value read or written for a plugin, without touching the disk.
   *
   * Synchronous on purpose: its callers are main-process code paths that
   * cannot await (a tray menu builder, a window-close policy).
   */
  snapshot(pluginId: string): unknown {
    return this.snapshots.get(pluginId) ?? null;
  }

  /** Observes writes, so host state derived from a plugin's data can be refreshed. */
  onChanged(listener: (pluginId: string, value: unknown) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private pathFor(pluginId: string): string {
    if (!safePluginId.test(pluginId)) {
      throw new PluginDataStoreError(`插件 id 不合法: ${pluginId}`);
    }
    return join(this.options.directory, `${pluginId}.json`);
  }

  /** Reads one JSON file, separating "there is no file" from "the file is unusable". */
  private async readJson(
    pluginId: string,
    path: string,
  ): Promise<{ present: boolean; value: unknown }> {
    try {
      return { present: true, value: JSON.parse(await readFile(path, "utf-8")) as unknown };
    } catch (error) {
      const code = (error as NodeJS.ErrnoException).code;
      if (code === "ENOENT") return { present: false, value: null };
      this.options.onError?.(pluginId, "read", error);
      return { present: true, value: null };
    }
  }
}
