import { createContext, useContext, useEffect, useSyncExternalStore } from "react";
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
  /** Stays on the task being read; moves to the first task only when it is gone from the list. */
  selectedId: string | null;
  roles: readonly RoleRecord[];
  rolesError: string;
};

type Attachment = { client: PluginRpcClient; host: PluginHostServices };

/**
 * State shared by the page and its sidebar, which the host mounts as siblings
 * with separate clients. The most recently attached client drives the task
 * list, so a reconnect hands over to a renewed client rather than an old one.
 */
class DashboardStore {
  private feed = new TaskFeed(listSource);
  private state: DashboardState = { list: this.feed.getSnapshot(), selectedId: null, roles: [], rolesError: "" };
  private listeners = new Set<() => void>();
  private attachments: Attachment[] = [];
  private driver: Attachment | null = null;
  private stopDriving: (() => void) | null = null;
  private rolesRequest = 0;

  constructor() {
    this.feed.subscribe(() => {
      const list = this.feed.getSnapshot();
      const tasks = list.value?.tasks;
      const kept = !tasks || tasks.some((task) => task.id === this.state.selectedId);
      this.commit({ ...this.state, list, selectedId: kept ? this.state.selectedId : (tasks[0]?.id ?? null) });
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

  /** Registers a mounted view; returns its detach function. */
  attach(client: PluginRpcClient, host: PluginHostServices) {
    const attachment = { client, host };
    this.attachments.push(attachment);
    this.followLatest();
    return () => {
      this.attachments = this.attachments.filter((item) => item !== attachment);
      this.followLatest();
    };
  }

  private followLatest() {
    const latest = this.attachments.at(-1) ?? null;
    if (latest === this.driver) return;
    this.stopDriving?.();
    this.driver = latest;
    this.stopDriving = latest ? this.drive(latest) : null;
  }

  private drive({ client, host }: Attachment) {
    void this.feed.start(client, host);
    this.loadRoles(host);
    const off = host.onEvent((event) => {
      if (event.method === "roles.updated") this.loadRoles(host);
    });
    return () => {
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

/** A store; the module keeps the one both mount points share, tests make their own. */
export function createDashboardStore() {
  return new DashboardStore();
}

const StoreContext = createContext(createDashboardStore());

/** Gives the components below a specific store (tests); without it they share the module's. */
export const DashboardStoreProvider = StoreContext.Provider;

/** Attaches a mounted view to the shared store and reads it. */
export function useDashboard(client: PluginRpcClient, host: PluginHostServices) {
  const store = useContext(StoreContext);
  useEffect(() => store.attach(client, host), [store, client, host]);
  return { state: useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot), store };
}
