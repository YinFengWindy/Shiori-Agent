import { useCallback, useEffect, useState } from "react";
import { errorMessage, type PluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { ScheduledTask, ScheduleTaskFormData } from "./types";

/** The plugin's own event after a role's jobs changed, started or finished running. */
export const scheduleTasksChangedEvent = "plugin.schedule.tasks.changed";

/** A mutation in flight; `taskId` is empty while creating. */
export type ScheduleOperation = { kind: "create" | "update" | "cancel"; taskId: string } | null;

// The block remounts whenever it moves between the task list and the whole
// panel. Starting from the role's last read keeps that move from flashing an
// empty list or bouncing an open detail back to the list.
const lastRead = new Map<string, ScheduledTask[]>();

async function readTasks(client: PluginRpcClient, roleId: string) {
  const { tasks } = await client.call<{ tasks: ScheduledTask[] }>("list", { role_id: roleId });
  lastRead.set(roleId, tasks);
  return tasks;
}

/**
 * The role's jobs, re-read whenever the plugin reports a change for the role,
 * and the block's mutations. `tasks` is `null` until the first read. The
 * caller keys the block by role, so one hook instance serves one role.
 */
export function useScheduledTasks(client: PluginRpcClient, host: PluginHostServices, roleId: string) {
  const [tasks, setTasks] = useState<ScheduledTask[] | null>(() => lastRead.get(roleId) ?? null);
  const [revision, setRevision] = useState(0);
  const [operation, setOperation] = useState<ScheduleOperation>(null);
  const [error, setError] = useState("");

  useEffect(() => host.onEvent((event) => {
    if (event.method === scheduleTasksChangedEvent && event.payload.role_id === roleId) {
      setRevision((current) => current + 1);
    }
  }), [host, roleId]);

  useEffect(() => {
    let cancelled = false;
    readTasks(client, roleId).then((next) => {
      if (!cancelled) setTasks(next);
    }, (cause: unknown) => {
      if (!cancelled) setError(errorMessage(cause, { includeDetail: true }));
    });
    return () => { cancelled = true; };
  }, [client, revision, roleId]);

  // Re-reads before resolving, so a view opened on the result finds its job.
  const mutate = useCallback(async (next: NonNullable<ScheduleOperation>, method: string, payload: Record<string, unknown>) => {
    setOperation(next);
    setError("");
    try {
      const result = await client.call<{ task?: ScheduledTask }>(method, { ...payload, role_id: roleId });
      setTasks(await readTasks(client, roleId));
      return result;
    } catch (cause) {
      setError(errorMessage(cause, { includeDetail: true }));
      throw cause;
    } finally {
      setOperation(null);
    }
  }, [client, roleId]);

  const create = useCallback(async (data: ScheduleTaskFormData) => {
    const { task } = await mutate({ kind: "create", taskId: "" }, "create", data);
    if (!task) throw new Error("计划任务创建结果缺少任务");
    return task;
  }, [mutate]);

  const update = useCallback(async (taskId: string, data: ScheduleTaskFormData) => {
    await mutate({ kind: "update", taskId }, "update", { ...data, task_id: taskId });
  }, [mutate]);

  const cancel = useCallback(async (taskId: string) => {
    await mutate({ kind: "cancel", taskId }, "cancel", { task_id: taskId });
  }, [mutate]);

  const clearError = useCallback(() => setError(""), []);

  return { tasks, operation, error, clearError, create, update, cancel };
}
