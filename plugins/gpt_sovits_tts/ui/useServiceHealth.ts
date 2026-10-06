import { useEffect, useRef, useState } from "react";
import { errorMessage, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { GptSoVitsHealth } from "../shared/contracts";

/** Checks API reachability and restores a quarantined instance only after explicit confirmation. */
export function useServiceHealth(client: PluginRpcClient) {
  const [health, setHealth] = useState<GptSoVitsHealth | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const revision = useRef(0);
  useEffect(() => { revision.current += 1; return () => { revision.current += 1; }; }, [client]);
  async function check(restarted = false) {
    const current = ++revision.current;
    setBusy(true); setError("");
    try {
      if (restarted) await client.call("reconnect", { service_restarted: true });
      const value = await client.call<GptSoVitsHealth>("health");
      if (current === revision.current) setHealth(value);
    } catch (cause) { if (current === revision.current) setError(errorMessage(cause)); }
    finally { if (current === revision.current) setBusy(false); }
  }
  function clear() {
    revision.current += 1;
    setHealth(null);
    setError("");
    setBusy(false);
  }
  return { health, error, busy, check, clear };
}
