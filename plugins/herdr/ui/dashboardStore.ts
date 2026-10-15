import { useEffect, useSyncExternalStore } from "react";
import { errorMessage, type PluginHostServices, type PluginRpcClient, type RoleRecord } from "@yinfengwindy/shiori-sdk";
import { TaskFeed, type FeedSource, type FeedState } from "./taskFeed";
import type { TaskListResponse } from "./types";

/** Keeps task objects whose revision did not advance, so unchanged rows keep their identity. */
export function mergeTaskList(current: TaskListResponse | null, next: TaskListResponse): TaskListResponse {
  if (!current || current.instance_id !== next.instance_id) return next;
  const known = new Map(current.tasks.map((task) => [task.id, task]));
  const tasks = next.tasks.map((task) => {
    const old = known.get(task.id);
    return old && old.revision >= task.revision ? old : task;
  });
  const unchanged = tasks.length === current.tasks.length && tasks.every((task, index) => task === current.tasks[index]);
  return unchanged ? current : { instance_id: next.instance_id, tasks };
}

const listSource: FeedSource<TaskListResponse> = {
  read: (client) => client.call<TaskListResponse>("tasks.list"),
  merge: mergeTaskList,
  invalidatedBy: (current, change) => {
    const known = current?.tasks.find((task) => task.id === change.task_id);
    return !known || change.revision > known.revision;
  },
};

/** What the sidebar and the page share. */
export type DashboardState = {
  list: FeedState<TaskListResponse>;
  /** Stays on the task the user is reading; only the first loaded task is picked automatically. */
  selectedId: string | null;
  roles: readonly RoleRecord[];
  rolesError: string;
};

type Attachment = { client: PluginRpcClient; host: PluginHostServices };

/**
 * The page and its sidebar are sibling mount points with separate clients, so
 * their shared state lives here. Whichever mounted first drives the task list
 * feed; when it leaves while the other stays, the other's client takes over.
 */
export class DashboardStore {
  private feed = new TaskFeed(listSource);
  private state: DashboardState = { list: this.feed.getSnapshot(), selectedId: null, roles: [], rolesError: "" };
  private listeners = new Set<() => void>();
  private attachments: Attachment[] = [];
  private stopDriver: (() => void) | null = null;
  private rolesRequest = 0;

  constructor() {
    this.feed.subscribe(() => {
      const list = this.feed.getSnapshot();
      this.commit({ ...this.state, list, selectedId: this.state.selectedId ?? list.value?.tasks[0]?.id ?? null });
    });
  }

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  getSnapshot = () => this.state;

  private commit(next: DashboardState) {
    const current = this.state;
    if (next.list === current.list && next.selectedId === current.selectedId && next.roles === current.roles && next.rolesError === current.rolesError) return;
    this.state = next;
    for (const listener of this.listeners) listener();
  }

  /** Selects a task to read; background updates never change it. */
  select = (taskId: string) => {
    this.commit({ ...this.state, selectedId: taskId });
  };

  /** Re-reads the task list now. */
  refresh = () => this.feed.refresh();

  /** Registers a mounted view; returns its detach function. */
  attach(client: PluginRpcClient, host: PluginHostServices) {
    const attachment = { client, host };
    this.attachments.push(attachment);
    if (this.attachments.length === 1) this.drive(attachment);
    return () => {
      const index = this.attachments.indexOf(attachment);
      if (index < 0) return;
      this.attachments.splice(index, 1);
      if (index > 0) return;
      this.stopDriver?.();
      this.stopDriver = null;
      if (this.attachments[0]) this.drive(this.attachments[0]);
    };
  }

  private drive({ client, host }: Attachment) {
    void this.feed.start(client, host);
    this.loadRoles(host);
    const off = host.onEvent((event) => {
      if (event.method === "roles.updated") this.loadRoles(host);
    });
    this.stopDriver = () => {
      off();
      this.feed.stop();
      this.rolesRequest++;
    };
  }

  private loadRoles(host: PluginHostServices) {
    const request = ++this.rolesRequest;
    host.listRoles().then(
      (roles) => { if (request === this.rolesRequest) this.commit({ ...this.state, roles, rolesError: "" }); },
      (error: unknown) => { if (request === this.rolesRequest) this.commit({ ...this.state, rolesError: errorMessage(error) }); },
    );
  }
}

/** The one store both Herdr mount points read. */
export let dashboardStore = new DashboardStore();

/** Test-only: a fresh store, as after an application start. */
export function resetDashboardStoreForTests() {
  dashboardStore = new DashboardStore();
}

/** Attaches a mounted view to the shared store and reads it. */
export function useDashboard(client: PluginRpcClient, host: PluginHostServices) {
  const store = dashboardStore;
  useEffect(() => store.attach(client, host), [store, client, host]);
  return { state: useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot), store };
}
