import { createContext, useContext, useEffect, useSyncExternalStore } from "react";
import { errorMessage, type PluginHostServices, type PluginRpcClient, type RoleRecord } from "@yinfengwindy/shiori-sdk";
import { firstSelection, type Selection } from "./agentSelectors";
import { mergeUnchanged, TaskFeed, type FeedSource, type FeedState } from "./taskFeed";
import type { AgentListResponse, TaskListResponse } from "./types";

/** How often an open page rereads Herdr, which has no change events. */
export const agentPollMs = 2500;

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

function agentListSource(pollMs: number): FeedSource<AgentListResponse> {
  return { read: (client) => client.call<AgentListResponse>("agents.list"), merge: mergeUnchanged, pollMs };
}

/** What the sidebar and the page share. */
export type DashboardState = {
  /** Plugin tasks, following `tasks.changed`. */
  list: FeedState<TaskListResponse>;
  /** The session's agents, polled while a view is attached. */
  agents: FeedState<AgentListResponse>;
  /** Picked once the agents are first known; never moved by background updates, even when its agent is gone. */
  selection: Selection | null;
  roles: readonly RoleRecord[];
  rolesError: string;
};

type Attachment = { client: PluginRpcClient; host: PluginHostServices };

/**
 * State shared by the page and its sidebar, which the host mounts as siblings
 * with separate clients. The most recently attached client drives the task
 * list and the agent polling, so a reconnect hands over to a renewed client
 * rather than an old one, and the polling ends when the last view detaches.
 */
class DashboardStore {
  private feed = new TaskFeed(listSource);
  private agentFeed: TaskFeed<AgentListResponse>;
  private state: DashboardState;
  private listeners = new Set<() => void>();
  private attachments: Attachment[] = [];
  private driver: Attachment | null = null;
  private stopDriving: (() => void) | null = null;
  private rolesRequest = 0;

  /** `pollMs` is also the agent detail's polling interval. */
  constructor(readonly pollMs = agentPollMs) {
    this.agentFeed = new TaskFeed(agentListSource(pollMs));
    this.state = { list: this.feed.getSnapshot(), agents: this.agentFeed.getSnapshot(), selection: null, roles: [], rolesError: "" };
    const update = () => {
      const list = this.feed.getSnapshot();
      const agents = this.agentFeed.getSnapshot();
      // Wait for the first agent answer, so a task is not picked over the agent carrying it.
      const settled = agents.value !== null || agents.error !== "";
      const selection = this.state.selection ?? (settled ? firstSelection(agents.value, list.value?.tasks ?? []) : null);
      this.commit({ ...this.state, list, agents, selection });
    };
    this.feed.subscribe(update);
    this.agentFeed.subscribe(update);
  }

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  getSnapshot = () => this.state;

  private commit(next: DashboardState) {
    const current = this.state;
    if (next.list === current.list && next.agents === current.agents && next.selection === current.selection && next.roles === current.roles && next.rolesError === current.rolesError) return;
    this.state = next;
    for (const listener of this.listeners) listener();
  }

  /** Selects an agent or an agentless task; background updates never change it. */
  select = (selection: Selection) => {
    this.commit({ ...this.state, selection });
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
    void this.agentFeed.start(client, host);
    this.loadRoles(host);
    const off = host.onEvent((event) => {
      if (event.method === "roles.updated") this.loadRoles(host);
    });
    return () => {
      off();
      this.feed.stop();
      this.agentFeed.stop();
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
export function createDashboardStore(pollMs?: number) {
  return new DashboardStore(pollMs);
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
