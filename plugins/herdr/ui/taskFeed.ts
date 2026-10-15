import { errorMessage, type PluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { TaskChange } from "./types";

/** A `useSyncExternalStore` snapshot: replaced only when something visible changed. */
export type FeedState<T> = {
  value: T | null;
  /** Last read failed or the bridge exited; the last value stays readable. */
  error: string;
  connected: boolean;
};

/** What one feed reads and how a newer response is told from an older one. */
export type FeedSource<T> = {
  read: (client: PluginRpcClient) => Promise<T>;
  /** Returns `current` itself when `next` carries nothing newer. */
  merge: (current: T | null, next: T) => T;
  /** Whether a `tasks.changed` invalidation can make `current` outdated; without it the feed does not subscribe. */
  invalidatedBy?: (current: T | null, change: TaskChange) => boolean;
  /** Reads again this long after each read settles, for state that has no events (Herdr agents). */
  pollMs?: number;
};

/** A `merge` for polled sources: keeps the current response when a poll brings nothing new, so the views keep their references. */
export function mergeUnchanged<T>(current: T | null, next: T): T {
  return current !== null && JSON.stringify(current) === JSON.stringify(next) ? current : next;
}

/** Message shown while the desktop bridge is down; recovery arrives as a new client. */
export const disconnectedMessage = "连接已断开";

/** One client's subscription; it ends when the feed stops, restarts or the bridge exits. */
type Session = {
  client: PluginRpcClient;
  dispose: Array<() => void>;
  exited: boolean;
  reading: boolean;
  again: boolean;
  timer?: ReturnType<typeof setTimeout>;
};

/**
 * Subscribe to `tasks.changed` before the first read, coalesce invalidations
 * into one read at a time, and never let an older response replace a newer
 * one. Stopping keeps the last value, so the client renewal that follows a
 * reconnect refreshes in place instead of flashing an empty view. A polled
 * source schedules its next read only after the previous one settles, so
 * reads never overlap; stopping or a bridge exit ends the polling.
 */
export class TaskFeed<T> {
  private state: FeedState<T> = { value: null, error: "", connected: true };
  private listeners = new Set<() => void>();
  private session: Session | null = null;

  constructor(private source: FeedSource<T>) {}

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  getSnapshot = () => this.state;

  private publish(patch: Partial<FeedState<T>>) {
    const next = { ...this.state, ...patch };
    if (next.value === this.state.value && next.error === this.state.error && next.connected === this.state.connected) return;
    this.state = next;
    for (const listener of this.listeners) listener();
  }

  private live(session: Session) {
    return this.session === session && !session.exited;
  }

  /** Starts a session for `client`, retiring the previous one. */
  async start(client: PluginRpcClient, host: PluginHostServices) {
    this.stop();
    const session: Session = { client, dispose: [], exited: false, reading: false, again: false };
    this.session = session;
    session.dispose.push(host.onEvent((event) => {
      if (event.method !== "bridge.exit" || !this.live(session)) return;
      // Responses still in flight from before the exit prove nothing about the connection.
      session.exited = true;
      clearTimeout(session.timer);
      this.publish({ connected: false, error: disconnectedMessage });
    }));
    try {
      const { invalidatedBy } = this.source;
      if (invalidatedBy) {
        const off = await client.events.on("tasks.changed", (payload) => {
          if (invalidatedBy(this.state.value, payload as TaskChange)) void this.refresh();
        });
        if (this.session !== session) { off(); return; }
        session.dispose.push(off);
      }
      await this.refresh();
    } catch (error) {
      if (this.live(session)) this.publish({ connected: false, error: errorMessage(error) });
    }
  }

  /** Reads now, or once more after the read in flight. */
  refresh = async () => {
    const session = this.session;
    if (!session || session.exited) return;
    if (session.reading) { session.again = true; return; }
    session.reading = true;
    try {
      do {
        session.again = false;
        const next = await this.source.read(session.client);
        if (!this.live(session)) return;
        this.apply(next);
      } while (session.again);
    } catch (error) {
      if (this.live(session)) this.publish({ connected: false, error: errorMessage(error) });
    } finally {
      session.reading = false;
      this.schedule(session);
    }
  };

  /** Queues the next poll; a read started meanwhile (an event) replaces the queued one. */
  private schedule(session: Session) {
    const { pollMs } = this.source;
    clearTimeout(session.timer);
    if (pollMs === undefined || !this.live(session)) return;
    session.timer = setTimeout(() => { void this.refresh(); }, pollMs);
  }

  /** Applies an authoritative response, e.g. the one a task action returned. */
  apply = (next: T) => {
    if (!this.session || this.session.exited) return;
    this.publish({ value: this.source.merge(this.state.value, next), error: "", connected: true });
  };

  /** Releases the subscription; the task itself keeps running in the backend. */
  stop() {
    const session = this.session;
    this.session = null;
    clearTimeout(session?.timer);
    for (const dispose of session?.dispose ?? []) dispose();
  }
}
