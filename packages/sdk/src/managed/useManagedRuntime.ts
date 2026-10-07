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
  const run = useCallback(async (action: ManagedRuntimeAction, source?: string) => {
    const current = revision.current;
    setPending(true); setActionError("");
    try {
      const value = await client.call<ManagedRuntimeStatus>(`runtime.${action}`, source ? { source } : {});
      if (revision.current === current) setStatus(value);
    } catch (cause) {
      if (revision.current === current) setActionError(errorMessage(cause));
    } finally {
      if (revision.current === current) setPending(false);
    }
  }, [client]);
  return { status, error: actionError || readError, pending, run };
}
