import { useCallback, useEffect, useRef, useState } from "react";
import type { PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { napCatPreparing } from "./qqStatusPresentation";

/** One managed instance's preparation, QR login, and connection state. */
export type ManagedStatus = {
  preparation: { stage: "idle" | "downloading" | "extracting" | "verifying" | "ready" | "error"; percent: number; version: string; error?: string };
  login: { phase: string; qrcode: string; error: string; login_phase?: string };
  connection: string;
  error: string;
  account_id?: string;
};

const FAST_POLL_MS = 1000;
const SLOW_POLL_MS = 3000;

/**
 * How soon to read the status again: every second while it is about to move
 * on its own (preparing, starting, fetching the QR, connecting after a scan),
 * every three while it waits on the user or holds still (QR shown, online, stopped).
 */
export function managedPollInterval(status: ManagedStatus | null) {
  if (!status) return FAST_POLL_MS;
  if (status.login.qrcode && status.login.phase !== "online") return SLOW_POLL_MS;
  const settling = napCatPreparing(status)
    || status.login.phase === "starting"
    || status.connection === "connecting"
    || status.login.phase === "login_required"
    || (status.login.phase === "online" && status.connection !== "online");
  return settling ? FAST_POLL_MS : SLOW_POLL_MS;
}

/** Polls only the selected QQ managed instance while its account detail is open. */
export function useManagedNapCat(client: PluginRpcClient, ref: string, enabled: boolean, onVerified?: (accountId: string) => void) {
  const [status, setStatus] = useState<ManagedStatus | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<"refresh" | "logout" | null>(null);
  const reportedAccount = useRef("");
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
    if (enabled && ref) void reload();
  }, [enabled, ref, reload]);

  // A changed interval re-arms the timer without an extra immediate read.
  const interval = managedPollInterval(status);
  useEffect(() => {
    if (!enabled || !ref) return;
    const timer = window.setInterval(() => void reload(), interval);
    return () => window.clearInterval(timer);
  }, [enabled, ref, reload, interval]);

  useEffect(() => {
    const accountId = status?.account_id;
    if (accountId && accountId !== reportedAccount.current) {
      reportedAccount.current = accountId;
      onVerified?.(accountId);
    }
  }, [status?.account_id, onVerified]);

  async function command(kind: "refresh" | "logout", method: string, payload: Record<string, unknown>) {
    setPending(kind);
    setError("");
    try {
      await client.call(method, payload);
      await reload();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setPending(null);
    }
  }
  const refreshQr = () => command("refresh", "accounts.refresh_qrcode", { ref });
  const logout = (accountId: string) => command("logout", "accounts.logout", { account_id: accountId });
  return { status, error, pending, busy: pending !== null, reload, refreshQr, logout };
}
