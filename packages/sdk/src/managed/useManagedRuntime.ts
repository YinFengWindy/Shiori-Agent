import { useCallback, useEffect, useRef, useState } from "react";
import type { PluginRpcClient } from "../rpc";
import { errorMessage } from "../errors";

/** State returned by the SDK's opt-in private runtime RPC controller. */
export type ManagedRuntimeStatus = {
  phase: "stopped" | "preparing" | "starting" | "removing" | "ready" | "cancelled" | "error";
  error: string; item: string; received: number; total: number;
  installed: boolean; running: boolean; busy: boolean; revision: string;
  /** Bytes of kept downloads a removal frees, also without an installation (3.1.1). */
  reclaimable: number;
  /** Whether unfinished preparation files are left over; never sized (3.1.1). */
  staging: boolean;
  /** Absolute install root holding downloads, staging and versions; "" while unreadable (3.1.1). */
  location: string;
  /** Whether a chosen location replaces the default one (3.1.1). */
  customized: boolean;
  /** Bytes the free-space check demands for a download on the install root's volume (3.1.1). */
  required: number;
  /** Bytes it demands for the provider's import: its single artifact in place, else a ZIP (3.1.1). */
  required_import: number;
  /** Free bytes on that volume; `null` when it is unavailable (3.1.1). */
  free: number | null;
  /** Whether anything installed or kept exists, i.e. 「删除环境」 has work (3.1.1). */
  removable: boolean;
  /** Whether the location can change: nothing installed or kept, no task (3.1.1). */
  relocatable: boolean;
};

/** A `runtime.*` action; `remove` deletes installed versions and caches (runtime API 3.1.1). */
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
  const call = useCallback(async (method: string, params: Record<string, string> = {}) => {
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
  /** Install under a dedicated directory inside `directory`, or the default without it (3.1.1). */
  const relocate = useCallback((directory?: string) => call("runtime.relocate", directory ? { directory } : {}), [call]);
  return { status, error: actionError || readError, pending, run, relocate };
}
