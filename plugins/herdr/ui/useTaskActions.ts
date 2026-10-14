import { useRef, useState } from "react";
import { errorMessage, type PluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { HerdrTask } from "./types";

/** One selected-task operation at a time; only authoritative snapshots change task state. */
export function useTaskActions(task: HerdrTask, client: PluginRpcClient, host: PluginHostServices, refresh: () => Promise<void>) {
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const busy = useRef(false);
  async function run(action: "continue" | "cancel" | "open_pr", requirement = "") {
    if (busy.current) return false;
    busy.current = true;
    setPending(action); setError("");
    try {
      if (action === "open_pr") await host.openExternal(task.pr_url);
      else await client.call(`tasks.${action}`, { task_id: task.id, requirement });
      await refresh();
      return true;
    } catch (reason) {
      setError(errorMessage(reason));
      return false;
    } finally { busy.current = false; setPending(""); }
  }
  return { pending, error, run, clearError: () => setError("") };
}
