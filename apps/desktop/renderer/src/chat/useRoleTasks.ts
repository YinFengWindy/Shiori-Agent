import { useCallback, useEffect, useState } from "react";
import type { RoleTask, ScheduleTaskFormData } from "../shared/types";

const refreshEventMethods = new Set(["session.updated", "chat.done", "chat.error", "roles.tasks.updated"]);

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

/** Owns loading and mutations for tasks belonging to the active role. */
export function useRoleTasks({ activeRoleId, bridgeReady, enabled }: {
  activeRoleId: string;
  bridgeReady: boolean;
  enabled: boolean;
}) {
  const [tasks, setTasks] = useState<RoleTask[]>([]);
  const [operation, setOperation] = useState<{ kind: "create" | "update" | "cancel"; taskId: string } | null>(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    if (!activeRoleId || !bridgeReady) {
      setTasks([]);
      return;
    }
    const response = await window.miraDesktop.invoke({ method: "roles.tasks.list", payload: { role_id: activeRoleId } });
    if (response.error) throw new Error(response.error.message);
    setTasks((response.payload.tasks as RoleTask[] | undefined) ?? []);
  }, [activeRoleId, bridgeReady]);

  useEffect(() => {
    setTasks([]);
    setError("");
    if (!enabled || !activeRoleId || !bridgeReady) return;
    const handleRefreshError = (refreshError: unknown) => setError(errorMessage(refreshError));
    void refresh().catch(handleRefreshError);
    const interval = window.setInterval(() => void refresh().catch(handleRefreshError), 3000);
    const off = window.miraDesktop.onEvent((event) => {
      if (!refreshEventMethods.has(event.method)) return;
      if (event.method === "roles.tasks.updated" && event.payload.role_id !== activeRoleId) return;
      void refresh().catch(handleRefreshError);
    });
    return () => {
      window.clearInterval(interval);
      off();
    };
  }, [activeRoleId, bridgeReady, enabled, refresh]);

  const mutate = useCallback(async (
    kind: "create" | "update" | "cancel",
    taskId: string,
    method: string,
    payload: Record<string, unknown>,
  ) => {
    if (!activeRoleId || !bridgeReady) throw new Error("桌面服务尚未就绪");
    setOperation({ kind, taskId });
    setError("");
    try {
      const response = await window.miraDesktop.invoke({
        method,
        payload: { ...payload, role_id: activeRoleId },
      });
      if (response.error) throw new Error(response.error.message);
      await refresh();
      return response.payload;
    } catch (mutationError) {
      setError(errorMessage(mutationError));
      throw mutationError;
    } finally {
      setOperation(null);
    }
  }, [activeRoleId, bridgeReady, refresh]);

  const create = useCallback(async (data: ScheduleTaskFormData) => {
    const payload = await mutate("create", "", "roles.tasks.create", data);
    return payload.task as RoleTask;
  }, [mutate]);

  const update = useCallback(async (taskId: string, data: ScheduleTaskFormData) => {
    const payload = await mutate("update", taskId, "roles.tasks.update", { ...data, task_id: taskId });
    return payload.task as RoleTask;
  }, [mutate]);

  const cancel = useCallback(async (taskId: string) => {
    await mutate("cancel", taskId, "roles.tasks.cancel", { task_id: taskId });
  }, [mutate]);

  const clearError = useCallback(() => setError(""), []);

  return { tasks, operation, error, clearError, create, update, cancel };
}
