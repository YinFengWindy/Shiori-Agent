import { useEffect, useRef, useState } from "react";
import { errorMessage, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { SenseVoiceHealth, SenseVoiceSettings } from "./contract";

/** Reads SenseVoice readiness for the current saved endpoint, clearing stale checks after save. */
export function useServiceHealth(client: PluginRpcClient, settings: SenseVoiceSettings | null) {
  const [health, setHealth] = useState<SenseVoiceHealth | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const revision = useRef(0);
  useEffect(() => {
    revision.current += 1;
    setHealth(null); setError(""); setBusy(false);
    return () => { revision.current += 1; };
  }, [client, settings]);
  async function check() {
    if (!settings) return;
    const current = ++revision.current;
    setBusy(true); setError("");
    try {
      const value = await client.call<SenseVoiceHealth>("health");
      if (current === revision.current) setHealth(value);
    } catch (cause) { if (current === revision.current) setError(errorMessage(cause)); }
    finally { if (current === revision.current) setBusy(false); }
  }
  return { health, error, busy, check };
}
