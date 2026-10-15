import { createFakeHostServices, createFakePluginClient } from "@yinfengwindy/shiori-sdk/testing";
import type { PluginEventHandler, RoleRecord } from "@yinfengwindy/shiori-sdk";
import type { TaskDetail, TaskListResponse, TaskSummary } from "./types";

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

/** A role record with only the fields Herdr reads. */
export function makeRole(id: string, name: string): RoleRecord {
  return { id, name, description: "", system_prompt: "", runtime_config: {}, avatar: null, avatar_abs: null, chat_background: null, chat_background_abs: null, illustrations: [], illustrations_abs: [], asset_categories: [], asset_category_bindings: {}, created_at: "", updated_at: "" };
}

/** Controllable plugin backend: answers list/get from local state and records every call and subscription. */
export function herdrBackend(tasks: TaskDetail[] = [makeDetail()], roles: RoleRecord[] = []) {
  const fake = createFakeHostServices({ listRoles: async () => roles });
  const handlers = new Set<PluginEventHandler>();
  const calls: Array<{ name: string; payload?: Record<string, unknown> }> = [];
  let state = { instance_id: "process-a", tasks };
  const summary = ({ id, title, status, finished, stage, progress_detail, progress_updated_at, role_id, agent, repository, branch, created_at, updated_at, revision }: TaskDetail): TaskSummary =>
    ({ id, title, status, finished, stage, progress_detail, progress_updated_at, role_id, agent, repository, branch, created_at, updated_at, revision });
  const createClient = () => createFakePluginClient({
    events: { on: async (_name, handler) => { handlers.add(handler); return () => { handlers.delete(handler); }; } },
    call: async <T,>(name: string, payload?: Record<string, unknown>) => {
      calls.push({ name, payload });
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
    emit(taskId: string, revision: number) {
      for (const handler of handlers) handler({ task_id: taskId, revision }, { id: "event", type: "event", method: "tasks.changed", payload: {} });
    },
  };
}
