import { createFakeHostServices, createFakePluginClient } from "@yinfengwindy/shiori-sdk/testing";
import type { PluginEventHandler } from "@yinfengwindy/shiori-sdk";
import type { HerdrTask, TaskSnapshot } from "./types";

/** Explicit task fixtures keep tests at the same public snapshot boundary as the UI. */
export function makeTask(patch: Partial<HerdrTask> = {}): HerdrTask {
  return { id: "task-a", run_id: "run-a", role_id: "role-a", thread_id: "thread-a", agent: "codex", requirement: "修复滚动位置", repository: "D:/repo", worktree: "D:/worktree", branch: "codex/task", status: "running", agent_state: "working", summary: "", validation: [], pr_url: "", error: "", report_error: "", output: "first output", created_at: "2026-10-14T10:00:00Z", updated_at: "2026-10-14T10:00:05Z", revision: 1, stage: "implementation", progress_updated_at: "2026-10-14T10:00:00Z", progress_notice: "", progress_events: [], can_continue: false, ...patch };
}

/** Controllable transport; it records requests and real subscribe/unsubscribe ownership. */
export function dashboardFixture(tasks: HerdrTask[] = [makeTask()]) {
  const fake = createFakeHostServices();
  const handlers = new Set<PluginEventHandler>();
  const calls: Array<{ name: string; payload?: Record<string, unknown> }> = [];
  let snapshot: TaskSnapshot = { instance_id: "process-a", tasks };
  let failed = false;
  const client = createFakePluginClient({
    events: { on: async (_name, handler) => { handlers.add(handler); return () => { handlers.delete(handler); }; } },
    call: async <T,>(name: string, payload?: Record<string, unknown>) => {
      calls.push({ name, payload });
      if (failed) throw new Error("offline");
      if (name === "tasks.snapshot") return structuredClone(snapshot) as T;
      return {} as T;
    },
  });
  return { fake, client, handlers, calls, setSnapshot: (value: TaskSnapshot) => { snapshot = value; }, fail: (value: boolean) => { failed = value; }, emit(taskId: string, revision: number) { for (const handler of handlers) handler({ task_id: taskId, revision }, { id: "event", type: "event", method: "tasks.changed", payload: {} }); } };
}
