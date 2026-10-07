import { useCallback, useEffect, useRef, useState } from "react";
import type { PluginRpcClient } from "../rpc";
import { errorMessage } from "../errors";

/** State returned by the SDK's opt-in private runtime RPC controller. */
export type ManagedRuntimeStatus = {
  phase: "stopped" | "preparing" | "starting" | "removing" | "ready" | "cancelled" | "error";
  error: string; item: string; received: number; total: number;
  installed: boolean; running: boolean; busy: boolean; revision: string;
  /** Bytes of kept downloads a removal frees, also without an installation (3.1.6). */
  reclaimable: number;
  /** Whether unfinished preparation files are left over; never sized (3.1.6). */
  staging: boolean;
  /** Absolute install root holding downloads, staging and versions (3.1.7). */
  location: string;
  /** Bytes a download preparation needs on the install root's volume (3.1.7). */
  required: number;
  /** Free bytes on that volume; `null` when it is unavailable (3.1.7). */
  free: number | null;
  /** Whether the location can change: nothing installed or kept, no task (3.1.7). */
  relocatable: boolean;
};

/** A `runtime.*` action; `remove` deletes installed versions and caches (runtime API 3.1.6). */
export type ManagedRuntimeAction = "prepare" | "start" | "stop" | "cancel" | "remove";

/** Polls background work; unmounting only discards UI results and does not cancel installation. */
export function useManagedRuntime(client: PluginRpcClient) {
  const [status, setStatus] = useState<ManagedRuntimeStatus | null>(null);
  const [readError, setReadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [pending, setPending] = useState(false);
  const revision = useRef(0);
  useEffect(() => {
    const current = ++revision.current;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function refresh() {
      try {
        const value = await client.call<ManagedRuntimeStatus>("runtime.status");
        if (revision.current === current) { setStatus(value); setReadError(""); }
      } catch (cause) {
        if (revision.current === current) setReadError(errorMessage(cause));
      } finally {
        if (revision.current === current) timer = setTimeout(() => void refresh(), 1000);
      }
    }
    setStatus(null); setReadError(""); setActionError(""); setPending(false);
    void refresh();
    return () => { revision.current += 1; clearTimeout(timer); };
  }, [client]);
  const call = useCallback(async (method: string, params: Record<string, string>) => {
    const current = revision.current;
    setPending(true); setActionError("");
    try {
      const value = await client.call<ManagedRuntimeStatus>(method, params);
      if (revision.current === current) setStatus(value);
    } catch (cause) {
      if (revision.current === current) setActionError(errorMessage(cause));
    } finally {
      if (revision.current === current) setPending(false);
    }
  }, [client]);
  /** `source` is the original absolute path of an imported package; it is never copied. */
  const run = useCallback((action: ManagedRuntimeAction, source?: string) => call(`runtime.${action}`, source ? { source } : {}), [call]);
  /** Install future preparations under a dedicated directory inside `directory` (3.1.7). */
  const relocate = useCallback((directory: string) => call("runtime.relocate", { directory }), [call]);
  return { status, error: actionError || readError, pending, run, relocate };
}
