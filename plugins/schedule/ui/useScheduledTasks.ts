import { useEffect, useState } from "react";
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

/** `change`, also kept as the role's last read. */
function remembered(roleId: string, change: TasksChange): TasksChange {
  return (current) => {
    const next = change(current);
    lastRead.set(roleId, next);
    return next;
  };
}

function withTask(task: ScheduledTask): TasksChange {
  return (current) => [...(current ?? []).filter((item) => item.id !== task.id), task];
}

async function readTasks(client: PluginRpcClient, roleId: string) {
  const { tasks } = await client.call<{ tasks: ScheduledTask[] }>("list", { role_id: roleId });
  return tasks;
}

/**
 * The role's jobs, re-read on mount, after each write and whenever the
 * plugin reports a change for the role, and the block's mutations. `tasks`
 * is `null` until the first read. The caller keys the block by role, so one
 * hook instance serves one role.
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

  useEffect(() => host.onEvent((event) => {
    if (event.method === scheduleTasksChangedEvent && event.payload.role_id === roleId) {
      setRevision((current) => current + 1);
    }
  }), [host, roleId]);

  useEffect(() => {
    let cancelled = false;
    readTasks(client, roleId).then((next) => {
      if (cancelled) return;
      setTasks(remembered(roleId, () => next));
      setLoadError("");
      const { openTaskId: openId, onOpenTaskGone: gone } = open.current;
      if (openId && !next.some((task) => task.id === openId)) gone();
    }, (cause: unknown) => {
      if (!cancelled) setLoadError(errorMessage(cause, { includeDetail: true }));
    });
    return () => { cancelled = true; };
  }, [client, open, revision, roleId]);

  /**
   * Runs one write. Only the write's own failure is a mutation error and
   * rejects. Once it succeeded, `applied` puts its result into the list right
   * away and a re-read follows; that read failing is only a load error, so
   * the user is never told to retry a write that already happened (which
   * would create a second job).
   */
  async function mutate<T>(next: NonNullable<ScheduleOperation>, write: () => Promise<T>, applied: (result: T) => TasksChange) {
    setOperation(next);
    setMutationError("");
    try {
      const result = await write();
      setTasks(remembered(roleId, applied(result)));
      setRevision((current) => current + 1);
      return result;
    } catch (cause) {
      setMutationError(errorMessage(cause, { includeDetail: true }));
      throw cause;
    } finally {
      setOperation(null);
    }
  }

  async function create(data: ScheduleTaskFormData) {
    const { task } = await mutate(
      { kind: "create", taskId: "" },
      () => client.call<{ task: ScheduledTask }>("create", { ...data, role_id: roleId }),
      (result) => withTask(result.task),
    );
    return task;
  }

  async function update(taskId: string, data: ScheduleTaskFormData) {
    await mutate(
      { kind: "update", taskId },
      () => client.call<{ task: ScheduledTask }>("update", { ...data, task_id: taskId, role_id: roleId }),
      (result) => withTask(result.task),
    );
  }

  async function cancel(taskId: string) {
    await mutate(
      { kind: "cancel", taskId },
      () => client.call<{ tasks: ScheduledTask[] }>("cancel", { task_id: taskId, role_id: roleId }),
      (result) => () => result.tasks,
    );
  }

  return {
    tasks,
    operation,
    error: mutationError || loadError,
    clearError: () => setMutationError(""),
    create,
    update,
    cancel,
  };
}
