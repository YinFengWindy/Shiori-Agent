import { BridgeError, chatTerminalEventMethods, errorMessage } from "@yinfengwindy/shiori-sdk";
import { useCallback, useEffect, useState } from "react";
import type { RoleTask } from "../shared/types";

const refreshEventMethods = new Set<string>(["session.updated", ...chatTerminalEventMethods, "roles.tasks.updated"]);

/** Owns loading and cancellation of the host's tasks belonging to the active role. */
export function useRoleTasks({ activeRoleId, bridgeReady, enabled }: {
  activeRoleId: string;
  bridgeReady: boolean;
  enabled: boolean;
}) {
  const [tasks, setTasks] = useState<RoleTask[]>([]);
  const [cancellingTaskId, setCancellingTaskId] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    if (!activeRoleId || !bridgeReady) {
      setTasks([]);
      return;
    }
    const response = await window.miraDesktop.invoke({ method: "roles.tasks.list", payload: { role_id: activeRoleId } });
    if (response.error) throw new BridgeError(response.error.message, response.error.code, response.error.details);
    setTasks((response.payload.tasks as RoleTask[] | undefined) ?? []);
  }, [activeRoleId, bridgeReady]);

  useEffect(() => {
    setTasks([]);
    setError("");
    if (!enabled || !activeRoleId || !bridgeReady) return;
    const handleRefreshError = (refreshError: unknown) => setError(errorMessage(refreshError, { includeDetail: true }));
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

  const cancel = useCallback(async (taskId: string) => {
    if (!activeRoleId || !bridgeReady) throw new Error("桌面服务尚未就绪");
    setCancellingTaskId(taskId);
    setError("");
    try {
      const response = await window.miraDesktop.invoke({
        method: "roles.tasks.cancel",
        payload: { role_id: activeRoleId, task_id: taskId },
      });
      if (response.error) throw new BridgeError(response.error.message, response.error.code, response.error.details);
      await refresh();
    } catch (cancelError) {
      setError(errorMessage(cancelError, { includeDetail: true }));
      throw cancelError;
    } finally {
      setCancellingTaskId("");
    }
  }, [activeRoleId, bridgeReady, refresh]);

  const clearError = useCallback(() => setError(""), []);

  return { tasks, cancellingTaskId, error, clearError, cancel };
}
