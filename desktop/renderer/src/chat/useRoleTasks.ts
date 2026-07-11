import { useCallback, useEffect, useState } from "react";
import type { RoleTask } from "../shared/types";

const refreshEventMethods = new Set(["session.updated", "chat.done", "chat.error", "roles.tasks.updated"]);

/** Owns loading, refreshing, and cancelling tasks for the active role. */
export function useRoleTasks({ activeRoleId, bridgeReady, enabled }: {
  activeRoleId: string;
  bridgeReady: boolean;
  enabled: boolean;
}) {
  const [tasks, setTasks] = useState<RoleTask[]>([]);
  const [cancellingTaskId, setCancellingTaskId] = useState("");

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
    if (!enabled || !activeRoleId || !bridgeReady) return;
    void refresh().catch(() => undefined);
    const interval = window.setInterval(() => void refresh().catch(() => undefined), 3000);
    const off = window.miraDesktop.onEvent((event) => {
      if (refreshEventMethods.has(event.method)) void refresh().catch(() => undefined);
    });
    return () => {
      window.clearInterval(interval);
      off();
    };
  }, [activeRoleId, bridgeReady, enabled, refresh]);

  const cancel = useCallback(async (taskId: string) => {
    if (!activeRoleId || !bridgeReady) return;
    setCancellingTaskId(taskId);
    try {
      const response = await window.miraDesktop.invoke({ method: "roles.tasks.cancel", payload: { role_id: activeRoleId, task_id: taskId } });
      if (response.error) throw new Error(response.error.message);
      setTasks((response.payload.tasks as RoleTask[] | undefined) ?? []);
    } finally {
      setCancellingTaskId("");
    }
  }, [activeRoleId, bridgeReady]);

  return { tasks, cancellingTaskId, cancel };
}
