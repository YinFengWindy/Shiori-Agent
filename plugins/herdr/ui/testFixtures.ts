import { createFakeHostServices, createFakePluginClient } from "@yinfengwindy/shiori-sdk/testing";
import type { PluginEventHandler, RoleRecord } from "@yinfengwindy/shiori-sdk";
import type { AgentDetailResponse, AgentListResponse, AgentSummary, AgentWorkspace, TaskDetail, TaskListResponse, TaskSummary } from "./types";

/** A task list entry as `tasks.list` returns it. */
export function makeSummary(patch: Partial<TaskSummary> = {}): TaskSummary {
  return {
    id: "task-a", title: "修复滚动位置", status: "running", finished: false, stage: "implementation", progress_detail: "改滚动容器",
    progress_updated_at: "2026-10-14T10:00:00Z", role_id: "role-a", agent: "codex", repository: "D:/repo", branch: "codex/task",
    created_at: "2026-10-14T09:00:00Z", updated_at: "2026-10-14T10:00:05Z", revision: 1, ...patch,
  };
}

/** A selected task as `tasks.get` returns it. */
export function makeDetail(patch: Partial<TaskDetail> = {}): TaskDetail {
  return {
    ...makeSummary(), run_id: "run-a", requirement: "修复滚动位置", worktree: "D:/worktree", output: "first output",
    progress_events: [], progress_notice: "", validation: [], summary: "", pr_url: "", error: "", report_error: "",
    can_continue: false, can_cancel: true, ...patch,
  };
}

/** An agent of the session as `agents.list` returns it. */
export function makeAgent(patch: Partial<AgentSummary> = {}): AgentSummary {
  return { pane_id: "wR:p2", workspace_id: "wR", agent: "claude", status: "working", title: "herdr插件问题", cwd: "D:/Coding/Shiori", task_id: null, ...patch };
}

/** A workspace group of `agents.list`. */
export function makeWorkspace(label: string, agents: AgentSummary[]): AgentWorkspace {
  return { workspace_id: agents[0]?.workspace_id ?? label, label, agents };
}

/** A role record with only the fields Herdr reads. */
export function makeRole(id: string, name: string): RoleRecord {
  return { id, name, description: "", system_prompt: "", runtime_config: {}, avatar: null, avatar_abs: null, chat_background: null, chat_background_abs: null, illustrations: [], illustrations_abs: [], asset_categories: [], asset_category_bindings: {}, created_at: "", updated_at: "" };
}

/**
 * Controllable plugin backend: answers the task and agent reads from local
 * state and records every call and subscription. Without workspaces the
 * session has no agents.
 */
export function herdrBackend(tasks: TaskDetail[] = [makeDetail()], roles: RoleRecord[] = [], workspaces: AgentWorkspace[] = []) {
  const fake = createFakeHostServices({ listRoles: async () => roles });
  const handlers = new Set<PluginEventHandler>();
  const calls: Array<{ name: string; payload?: Record<string, unknown> }> = [];
  let state = { instance_id: "process-a", tasks };
  let agents: AgentListResponse = { session: "default", workspaces };
  let agentsError: Error | null = null;
  const summary = ({ id, title, status, finished, stage, progress_detail, progress_updated_at, role_id, agent, repository, branch, created_at, updated_at, revision }: TaskDetail): TaskSummary =>
    ({ id, title, status, finished, stage, progress_detail, progress_updated_at, role_id, agent, repository, branch, created_at, updated_at, revision });
  const createClient = () => createFakePluginClient({
    events: { on: async (_name, handler) => { handlers.add(handler); return () => { handlers.delete(handler); }; } },
    call: async <T,>(name: string, payload?: Record<string, unknown>) => {
      calls.push({ name, payload });
      if (name === "agents.list") {
        if (agentsError) throw agentsError;
        return structuredClone(agents) as T;
      }
      if (name === "agents.get") {
        const agent = agents.workspaces.flatMap((group) => group.agents).find((item) => item.pane_id === payload?.pane_id) ?? null;
        const task = state.tasks.find((item) => item.id === agent?.task_id) ?? null;
        return structuredClone({ session: agents.session, agent, output: agent ? `output of ${agent.pane_id}` : "", task } satisfies AgentDetailResponse) as T;
      }
      if (name === "tasks.list") return structuredClone({ instance_id: state.instance_id, tasks: state.tasks.map(summary) } satisfies TaskListResponse) as T;
      const task = state.tasks.find((item) => item.id === payload?.task_id);
      if (!task) throw new Error("任务不存在");
      return structuredClone({ instance_id: state.instance_id, task }) as T;
    },
  });
  return {
    fake,
    client: createClient(),
    /** A new client on the same backend, as the host hands out after the bridge comes back. */
    renewClient: createClient,
    handlers,
    calls,
    setTasks(next: TaskDetail[]) { state = { ...state, tasks: next }; },
    setWorkspaces(next: AgentWorkspace[]) { agents = { ...agents, workspaces: next }; },
    /** Makes `agents.list` fail, as an unavailable session does; null recovers. */
    failAgents(error: Error | null) { agentsError = error; },
    emit(taskId: string, revision: number) {
      for (const handler of handlers) handler({ task_id: taskId, revision }, { id: "event", type: "event", method: "tasks.changed", payload: {} });
    },
  };
}
