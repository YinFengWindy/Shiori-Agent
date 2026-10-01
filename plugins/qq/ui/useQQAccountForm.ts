import { useEffect, useRef, useState } from "react";
import { errorMessage, type HostInlineErrorProps, type PluginRpcClient } from "@shiori/sdk";

type ConnectionSettings = { ref: string };

type FormOptions = {
  accountId?: string;
  /** Role that owns the managed instance and its eventual verified account. */
  roleId: string;
  client: PluginRpcClient;
  onChanged: (accountId?: string) => void;
  onCleanupError: (failure: unknown) => void;
};

/** Re-reads the managed status, so the in-flight state only clears once the new state is known. */
type RefreshStatus = () => Promise<void>;

/**
 * Loads one managed instance and exposes explicit start/stop commands.
 * `pending` names the command in flight for the status card.
 */
export function useQQAccountForm({ accountId, roleId, client, onChanged, onCleanupError }: FormOptions) {
  const active = useRef(false);
  const [savedRef, setSavedRef] = useState("");
  const [managedAvailable, setManagedAvailable] = useState(false);
  const [pending, setPending] = useState<"connect" | "disconnect" | null>(null);
  // Settings load on mount, so nothing reads "unsupported" before they arrive.
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Pick<HostInlineErrorProps, "message" | "detail"> | null>(null);

  useEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);

  useEffect(() => {
    let current = true;
    setError(null);
    setSavedRef("");
    setLoading(true);
    const payload = accountId ? { account_id: accountId } : undefined;
    void client.call<{ account?: ConnectionSettings; managed_available: boolean }>("accounts.settings", payload)
      .then(({ account, managed_available }) => {
        if (!current) return;
        setManagedAvailable(managed_available);
        setSavedRef(account?.ref ?? "");
      })
      .catch((failure: unknown) => { if (current) setError({ message: "QQ 账号设置读取失败", detail: errorMessage(failure, { includeDetail: true }) }); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [accountId, client]);

  const ref = savedRef;

  async function run(kind: "connect" | "disconnect", operation: () => Promise<void>) {
    if (pending) return;
    setPending(kind);
    setError(null);
    try { await operation(); }
    catch (failure) { if (active.current) setError({ message: kind === "connect" ? "QQ 连接未完成" : "QQ 断开未完成", detail: errorMessage(failure, { includeDetail: true }) }); }
    finally { if (active.current) setPending(null); }
  }

  /** Starts the saved instance, or begins a temporary login when adding. */
  const start = (refresh?: RefreshStatus) => run("connect", async () => {
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
    await refresh?.();
  });
  /**
   * Disconnects a verified account by its ID — known from the managed status
   * as soon as the login is verified, before the host list has it — and only
   * stops a still-unverified temporary login by its ref.
   */
  const disconnect = (verifiedAccountId: string, refresh?: RefreshStatus) => run("disconnect", async () => {
    if (verifiedAccountId) await client.call("accounts.disconnect", { account_id: verifiedAccountId });
    else if (ref) await client.call("accounts.stop", { ref, role_id: roleId });
    else return;
    onChanged();
    await refresh?.();
  });

  return { ref, pending, busy: pending !== null, loading, error, managedAvailable, client, start, disconnect, onVerified: onChanged };
}
