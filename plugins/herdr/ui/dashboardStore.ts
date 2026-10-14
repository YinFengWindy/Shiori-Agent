import { errorMessage, type PluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { HerdrTask, TaskSnapshot } from "./types";

/** Stable snapshots are required by useSyncExternalStore. */
export type DashboardState = { tasks: readonly HerdrTask[]; loading: boolean; error: string; connected: boolean };

/** Subscribe before reading, coalesce invalidations, and never apply an older task revision. */
export class DashboardStore {
  private state: DashboardState = { tasks: [], loading: true, error: "", connected: true };
  private listeners = new Set<() => void>();
  private instanceId = "";
  private generation = 0;
  private connectionVersion = 0;
  private active = false;
  private inFlight = false;
  private again = false;
  private unsubscribe: (() => void) | null = null;
  private unsubscribeHost: (() => void) | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(private client: PluginRpcClient, private host: PluginHostServices) {}

  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  getSnapshot = () => this.state;

  private publish(next: DashboardState) {
    if (next.tasks === this.state.tasks && next.loading === this.state.loading && next.error === this.state.error && next.connected === this.state.connected) return;
    this.state = next;
    for (const listener of this.listeners) listener();
  }

  /** A fresh mount/client always takes an authoritative snapshot. */
  async start() {
    if (this.active) return;
    this.active = true;
    const generation = ++this.generation;
    this.unsubscribeHost = this.host.onEvent((event) => {
      if (event.method === "bridge.exit") { ++this.connectionVersion; this.publish({ ...this.state, connected: false, error: "连接已断开" }); }
      if (event.method === "bridge.ready" || event.method === "runtime.applied") { ++this.connectionVersion; void this.refresh(); }
    });
    try {
      const unsubscribe = await this.client.events.on("tasks.changed", (payload) => {
        const known = this.state.tasks.find((task) => task.id === payload.task_id);
        if (known && typeof payload.revision === "number" && payload.revision <= known.revision) return;
        void this.refresh();
      });
      if (!this.active || generation !== this.generation) { unsubscribe(); return; }
      this.unsubscribe = unsubscribe;
      await this.refresh();
      if (this.active && generation === this.generation) this.timer = setInterval(() => { void this.refresh(); }, 10_000);
    } catch (error) {
      if (this.active && generation === this.generation) this.publish({ ...this.state, loading: false, connected: false, error: errorMessage(error) });
    }
  }

  /** Read-only retries also repair a lost invalidation event or temporary disconnect. */
  refresh = async () => {
    if (!this.active) return;
    if (this.inFlight) { this.again = true; return; }
    const generation = this.generation;
    const connectionVersion = this.connectionVersion;
    this.inFlight = true;
    try {
      do {
        this.again = false;
        const snapshot = await this.client.call<TaskSnapshot>("tasks.snapshot");
        if (!this.active || generation !== this.generation || connectionVersion !== this.connectionVersion) return;
        const previous = new Map(this.state.tasks.map((task) => [task.id, task]));
        const sameInstance = snapshot.instance_id === this.instanceId;
        const tasks = snapshot.tasks.map((task) => {
          const old = previous.get(task.id);
          return sameInstance && old && old.revision >= task.revision ? old : task;
        }).sort((a, b) => b.created_at.localeCompare(a.created_at));
        const unchanged = tasks.length === this.state.tasks.length && tasks.every((task, index) => task === this.state.tasks[index]);
        this.instanceId = snapshot.instance_id;
        this.publish({ tasks: unchanged ? this.state.tasks : tasks, loading: false, error: "", connected: true });
      } while (this.again && this.active && generation === this.generation);
    } catch (error) {
      if (this.active && generation === this.generation && connectionVersion === this.connectionVersion) this.publish({ ...this.state, loading: false, connected: false, error: errorMessage(error) });
    } finally {
      if (generation === this.generation) {
        this.inFlight = false;
        if (this.again) { this.again = false; void this.refresh(); }
      }
    }
  };

  /** Leaving the page only closes view subscriptions, never task execution. */
  stop() {
    this.active = false;
    ++this.generation;
    this.inFlight = false;
    this.again = false;
    this.unsubscribe?.(); this.unsubscribe = null;
    this.unsubscribeHost?.(); this.unsubscribeHost = null;
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}
