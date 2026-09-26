import { useCallback, useEffect, useState } from "react";
import type { PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";

type ManagedStatus = {
  preparation: { stage: string; percent: number; version: string; error?: string };
  login: { phase: string; qrcode: string; error: string; login_phase?: string };
  connection: string;
  error: string;
};

/** Polls only the selected QQ managed instance while its account detail is open. */
export function useManagedNapCat(client: PluginRpcClient, ref: string, enabled: boolean) {
  const [status, setStatus] = useState<ManagedStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const reload = useCallback(async () => {
    if (!enabled || !ref) return;
    try {
      const next = await client.call<ManagedStatus>("accounts.managed_status", { ref });
      setStatus(next);
      setError("");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }, [client, enabled, ref]);

  useEffect(() => {
    if (!enabled || !ref) return;
    void reload();
    const timer = window.setInterval(() => void reload(), 3000);
    return () => window.clearInterval(timer);
  }, [enabled, ref, reload]);

  const refreshQr = async () => {
    setBusy(true);
    setError("");
    try {
      await client.call("accounts.refresh_qrcode", { ref });
      await reload();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  };
  const logout = async (accountId: string) => {
    setBusy(true);
    setError("");
    try {
      await client.call("accounts.logout", { account_id: accountId });
      await reload();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  };
  return { status, error, busy, refreshQr, logout };
}
