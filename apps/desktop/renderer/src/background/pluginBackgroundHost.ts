import { BackgroundEffectScope } from "./backgroundEffectScope";
import type { BackgroundCtx, PluginBackgroundEntry } from "./pluginBackgroundRegistry";

/** A registry surface narrow enough to fake in tests without the real singleton. */
export type PluginBackgroundRegistryLike = { list(): PluginBackgroundEntry[] };

export type PluginBackgroundHostDeps = {
  registry: PluginBackgroundRegistryLike;
  /** Fetches the current enabled-plugin roster; called at startup and on every reconcile. */
  listEnabledPluginIds(): Promise<Set<string>>;
  /** Subscribes to whatever signals "the enabled roster may have changed"; returns an unsubscribe. */
  subscribeRosterChanged(listener: (available?: boolean) => void): () => void;
  createCtx(pluginId: string, scope: BackgroundEffectScope): BackgroundCtx;
  /** Reports a failure. `pluginId` is empty for `"roster"`, which is not attributable to one plugin. */
  onError?(pluginId: string, phase: "setup" | "dispose" | "roster", error: unknown): void;
};

/**
 * Runs every registered `app.background` contribution whose plugin is
 * currently enabled, and tears it down the moment it is not.
 *
 * This is the piece that makes "停用插件后...订阅全部回收" (#181's acceptance
 * criterion) real rather than aspirational: disabling a plugin disposes its
 * `BackgroundEffectScope`, which — per that type's own contract — always
 * unsubscribes its backend event listeners before running any other cleanup
 * (#227).
 *
 * This window has no `pluginEnabledStateStore` of its own (that store is
 * populated by the *main window's* plugin management UI — see
 * `usePluginManagementController.ts` — and this is a different renderer
 * entirely). Instead of duplicating that store, this host asks the backend
 * directly (`listEnabledPluginIds`, backed by `plugins.list`) at startup and
 * again whenever `subscribeRosterChanged` fires. In `main.ts` that signal is
 * the `runtime.applied` bridge event — which, note, did *not* previously fire
 * for a plugin toggle: it is published explicitly per request branch in
 * `desktop_bridge/runtime/service.py`, and `plugins.setEnabled` reached no
 * publish at all until #226 added one. See `main.ts`'s `subscribeRosterChanged`
 * for why that publish must not be "cleaned up" as redundant.
 */
export class PluginBackgroundHost {
  private readonly running = new Map<string, BackgroundEffectScope>();
  private unsubscribeRosterChanged: (() => void) | null = null;
  // Serializes reconcile() calls: a `runtime.applied` burst (e.g. several
  // settings changes landing close together) must not run two reconciles
  // concurrently against the same `running` map.
  private queue: Promise<void> = Promise.resolve();

  constructor(private readonly deps: PluginBackgroundHostDeps) {}

  /** Runs the first reconcile and starts listening for roster changes. */
  async start(): Promise<void> {
    await this.reconcile();
    this.unsubscribeRosterChanged = this.deps.subscribeRosterChanged((available = true) => {
      this.enqueue(() => available ? this.reconcile(true) : this.teardownAll());
    });
  }

  /** Tears down every currently running plugin and stops listening for roster changes. */
  async stop(): Promise<void> {
    this.unsubscribeRosterChanged?.();
    this.unsubscribeRosterChanged = null;
    await this.enqueue(() => this.teardownAll());
  }

  /** Plugin ids with a currently running background scope; test/diagnostic use. */
  runningPluginIds(): string[] {
    return [...this.running.keys()];
  }

  private enqueue(task: () => Promise<void>): Promise<void> {
    // The stored chain and the returned promise are deliberately *different*
    // promises, matching `DesktopPetController.enqueue`. Storing the same one
    // would leave `this.queue` rejected and unobserved whenever a task throws
    // — an unhandled rejection — because the roster-changed subscriber below
    // fires and forgets. The stored chain is therefore always-resolved, while
    // the caller still gets a promise it can await and observe.
    const next = this.queue.then(task, task);
    this.queue = next.catch(() => undefined);
    return next;
  }

  private async reconcile(replaceGeneration = false): Promise<void> {
    // Reported rather than allowed to escape: `subscribeRosterChanged`'s
    // listener cannot await this, so a roster fetch that throws would
    // otherwise fail silently and leave the running set stale.
    let enabled: Set<string>;
    try {
      enabled = await this.deps.listEnabledPluginIds();
    } catch (error) {
      this.deps.onError?.("", "roster", error);
      return;
    }
    if (replaceGeneration) {
      for (const pluginId of this.running.keys()) await this.teardown(pluginId);
    }
    for (const entry of this.deps.registry.list()) {
      const shouldRun = enabled.has(entry.pluginId);
      const isRunning = this.running.has(entry.pluginId);
      if (shouldRun && !isRunning) {
        await this.setup(entry);
      } else if (!shouldRun && isRunning) {
        await this.teardown(entry.pluginId);
      }
    }
  }

  private async teardownAll(): Promise<void> {
    await Promise.all([...this.running.keys()].map((pluginId) => this.teardown(pluginId)));
  }

  private async setup(entry: PluginBackgroundEntry): Promise<void> {
    const scope = new BackgroundEffectScope();
    this.running.set(entry.pluginId, scope);
    try {
      await entry.setup(this.deps.createCtx(entry.pluginId, scope));
    } catch (error) {
      // A half-finished `setup` still registered whatever it got through
      // before throwing, so the scope has to be disposed rather than merely
      // dropped: forgetting it here would strand those subscriptions with no
      // reference left to clean them up, and a later disable could not reach
      // them either. Mirrors the backend kernel's `_rollback_failed_load`,
      // which disposes the handle's effects on the same failure.
      this.running.delete(entry.pluginId);
      const disposeErrors = await scope.disposeAll();
      this.deps.onError?.(entry.pluginId, "setup", error);
      for (const disposeError of disposeErrors) {
        this.deps.onError?.(entry.pluginId, "dispose", disposeError);
      }
    }
  }

  private async teardown(pluginId: string): Promise<void> {
    const scope = this.running.get(pluginId);
    if (!scope) return;
    this.running.delete(pluginId);
    const errors = await scope.disposeAll();
    for (const error of errors) this.deps.onError?.(pluginId, "dispose", error);
  }
}
