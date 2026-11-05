import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { rpcMethods, type RpcMethod } from "../rpcMethods.generated";
import type { McpSnapshot } from "./types";

/** Read after subscriptions and mutations; obsolete reads cannot replace newer state. */
export function useMcpServers(client: PluginRpcClient) {
  const [snapshot, setSnapshot] = useState<McpSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const sequence = useRef(0);
  const reload = useCallback(async () => {
    const read = ++sequence.current;
    try {
      const next = await client.call<McpSnapshot>(rpcMethods["servers.list"]);
      if (read === sequence.current) { setSnapshot(next); setError(null); }
    } catch (cause) { if (read === sequence.current) setError(errorMessage(cause)); }
  }, [client]);
  useEffect(() => {
    let disposed = false;
    let unsubscribe: (() => void) | undefined;
    client.events.on("servers.changed", () => { void reload(); }).then((remove) => {
      if (disposed) remove(); else { unsubscribe = remove; void reload(); }
    }).catch((cause: unknown) => { if (!disposed) setError(errorMessage(cause)); });
    return () => { disposed = true; sequence.current += 1; unsubscribe?.(); };
  }, [client, reload]);
  const run = async (method: RpcMethod, payload: Record<string, unknown>) => {
    setBusy(true); setError(null); ++sequence.current;
    try {
      const next = await client.call<McpSnapshot>(method, payload);
      ++sequence.current; setSnapshot(next);
      return true;
    } catch (cause) { setError(errorMessage(cause)); return false; }
    finally { setBusy(false); }
  };
  return { snapshot, error, busy, reload, run };
}
