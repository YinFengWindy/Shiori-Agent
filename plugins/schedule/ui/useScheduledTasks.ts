import { useCallback, useEffect, useState } from "react";
import { errorMessage, useLatestRef, type PluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { ScheduledTask, ScheduleTaskFormData } from "./types";

/** The plugin's own event after a role's jobs changed, started or finished running. */
export const scheduleTasksChangedEvent = "plugin.schedule.tasks.changed";

/** A mutation in flight; `taskId` is empty while creating. */
export type ScheduleOperation = { kind: "create" | "update" | "cancel"; taskId: string } | null;

type TasksChange = (current: ScheduledTask[] | null) => ScheduledTask[];

// The host remounts the block whenever it moves between the task list and
// the whole panel (list → detail, form → list). Starting from the role's last
// read avoids showing an empty group (count 0) or a blank panel for one RPC
// on every such move; a fresh read still follows each mount.
const lastRead = new Map<string, ScheduledTask[]>();

function withTask(task: ScheduledTask): TasksChange {
  return (current) => [...(current ?? []).filter((item) => item.id !== task.id), task];
}

/**
 * The role's jobs, re-read whenever the plugin reports a change for the role,
 * and the block's mutations. `tasks` is `null` until the first read. The
 * caller keys the block by role, so one hook instance serves one role.
 *
 * `openTaskId` is the job the block's open view shows. When a read no longer
 * has it (cancelled elsewhere, or it fired for the last time),
 * `onOpenTaskGone` runs with that read, so the block hands the panel back in
 * the same update instead of rendering a view without its job.
 */
export function useScheduledTasks(client: PluginRpcClient, host: PluginHostServices, roleId: string, { openTaskId, onOpenTaskGone }: {
  openTaskId: string;
  onOpenTaskGone: () => void;
}) {
  const [tasks, setTasks] = useState<ScheduledTask[] | null>(() => lastRead.get(roleId) ?? null);
  const [revision, setRevision] = useState(0);
  const [operation, setOperation] = useState<ScheduleOperation>(null);
  const [loadError, setLoadError] = useState("");
  const [mutationError, setMutationError] = useState("");
  const open = useLatestRef({ openTaskId, onOpenTaskGone });

  const keep = useCallback((change: TasksChange) => {
    setTasks((current) => {
      const next = change(current);
      lastRead.set(roleId, next);
      return next;
    });
  }, [roleId]);

  const read = useCallback(async () => {
    const { tasks: next } = await client.call<{ tasks: ScheduledTask[] }>("list", { role_id: roleId });
    keep(() => next);
    setLoadError("");
    const { openTaskId: openId, onOpenTaskGone: gone } = open.current;
    if (openId && !next.some((task) => task.id === openId)) gone();
  }, [client, keep, open, roleId]);

  useEffect(() => host.onEvent((event) => {
    if (event.method === scheduleTasksChangedEvent && event.payload.role_id === roleId) {
      setRevision((current) => current + 1);
    }
  }), [host, roleId]);

  useEffect(() => {
    let cancelled = false;
    read().catch((cause: unknown) => {
      if (!cancelled) setLoadError(errorMessage(cause, { includeDetail: true }));
    });
    return () => { cancelled = true; };
  }, [read, revision]);

  /**
   * Runs one write. Only the write's own failure is a mutation error and
   * rejects. Once it succeeded, `applied` puts its result into the list and a
   * failing re-read is just a load error, so the user is never told to retry
   * a write that already happened (which would create a second job).
   */
  const mutate = useCallback(async <T>(next: NonNullable<ScheduleOperation>, write: () => Promise<T>, applied: (result: T) => TasksChange) => {
    setOperation(next);
    setMutationError("");
    try {
      let result: T;
      try {
        result = await write();
      } catch (cause) {
        setMutationError(errorMessage(cause, { includeDetail: true }));
        throw cause;
      }
      keep(applied(result));
      await read().catch((cause: unknown) => setLoadError(errorMessage(cause, { includeDetail: true })));
      return result;
    } finally {
      setOperation(null);
    }
  }, [keep, read]);

  const create = useCallback(async (data: ScheduleTaskFormData) => {
    const { task } = await mutate(
      { kind: "create", taskId: "" },
      () => client.call<{ task: ScheduledTask }>("create", { ...data, role_id: roleId }),
      (result) => withTask(result.task),
    );
    return task;
  }, [client, mutate, roleId]);

  const update = useCallback(async (taskId: string, data: ScheduleTaskFormData) => {
    await mutate(
      { kind: "update", taskId },
      () => client.call<{ task: ScheduledTask }>("update", { ...data, task_id: taskId, role_id: roleId }),
      (result) => withTask(result.task),
    );
  }, [client, mutate, roleId]);

  const cancel = useCallback(async (taskId: string) => {
    await mutate(
      { kind: "cancel", taskId },
      () => client.call<{ tasks: ScheduledTask[] }>("cancel", { task_id: taskId, role_id: roleId }),
      (result) => () => result.tasks,
    );
  }, [client, mutate, roleId]);

  const clearError = useCallback(() => setMutationError(""), []);

  return { tasks, operation, error: mutationError || loadError, clearError, create, update, cancel };
}
