import { useEffect, useRef, useState } from "react";
import type { PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";

type ConnectionSettings = { ref: string };

type FormOptions = {
  accountId?: string;
  /** Role that owns the managed instance and its eventual verified account. */
  roleId: string;
  client: PluginRpcClient;
  onChanged: (accountId?: string) => void;
  onCleanupError: (failure: unknown) => void;
};

/** Loads one managed instance and exposes explicit start/stop commands. */
export function useQQAccountForm({ accountId, roleId, client, onChanged, onCleanupError }: FormOptions) {
  const active = useRef(false);
  const [savedRef, setSavedRef] = useState("");
  const [managedAvailable, setManagedAvailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);

  useEffect(() => {
    let current = true;
    setError("");
    setSavedRef("");
    setLoading(true);
    const payload = accountId ? { account_id: accountId } : undefined;
    void client.call<{ account?: ConnectionSettings; managed_available: boolean }>("accounts.settings", payload)
      .then(({ account, managed_available }) => {
        if (!current) return;
        setManagedAvailable(managed_available);
        setSavedRef(account?.ref ?? "");
      })
      .catch((failure: unknown) => { if (current) setError(failure instanceof Error ? failure.message : String(failure)); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [accountId, client]);

  const ref = savedRef;

  async function run(operation: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try { await operation(); }
    catch (failure) { if (active.current) setError(failure instanceof Error ? failure.message : String(failure)); }
    finally { if (active.current) setBusy(false); }
  }

  const start = () => run(async () => {
    const managedRef = ref || (await client.call<{ ref: string }>("accounts.begin", {
      role_id: roleId,
    })).ref;
    if (!active.current) {
      try { await client.call("accounts.cancel", { ref: managedRef, role_id: roleId }); }
      catch (failure) { onCleanupError(failure); }
      return;
    }
    setSavedRef(managedRef);
    const result = await client.call<{ account_id: string }>("accounts.start", { ref: managedRef, role_id: roleId });
    if (!active.current) {
      try { await client.call("accounts.cancel", { ref: managedRef, role_id: roleId }); }
      catch (failure) { onCleanupError(failure); }
      return;
    }
    if (result.account_id) onChanged(result.account_id);
  });
  const disconnect = () => run(async () => {
    if (accountId) await client.call("accounts.disconnect", { account_id: accountId });
    else if (ref) await client.call("accounts.stop", { ref, role_id: roleId });
    else return;
    onChanged();
  });

  return { ref, busy, loading, error, managedAvailable, client, start, disconnect, onVerified: onChanged };
}
