import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage, type HostInlineErrorProps, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
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
 * How soon to read the status again: every three seconds once it holds still
 * (connected, or stopped), otherwise every second — including while a QR code
 * is shown, so a finished scan shows up promptly.
 */
export function managedPollInterval(status: ManagedStatus | null) {
  if (!status || napCatPreparing(status) || status.connection === "connecting") return FAST_POLL_MS;
  const settled = status.login.phase === "stopped"
    || (status.login.phase === "online" && status.connection === "online");
  return settled ? SLOW_POLL_MS : FAST_POLL_MS;
}

/** Polls only the selected QQ managed instance while its account detail is open. */
export function useManagedNapCat(client: PluginRpcClient, ref: string, enabled: boolean, onVerified?: (accountId: string) => void) {
  const [status, setStatus] = useState<ManagedStatus | null>(null);
  const [error, setError] = useState<Pick<HostInlineErrorProps, "message" | "detail"> | null>(null);
  const [pending, setPending] = useState<"refresh" | "logout" | null>(null);
  const reportedAccount = useRef("");
  const reload = useCallback(async () => {
    if (!enabled || !ref) return;
    try {
      const next = await client.call<ManagedStatus>("accounts.managed_status", { ref });
      setStatus(next);
      setError(null);
    } catch (failure) {
      setError({ message: "QQ 连接状态读取失败", detail: errorMessage(failure, { includeDetail: true }) });
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
    setError(null);
    try {
      await client.call(method, payload);
      await reload();
    } catch (failure) {
      setError({ message: kind === "refresh" ? "QQ 登录二维码刷新失败" : "QQ 退出登录未完成", detail: errorMessage(failure, { includeDetail: true }) });
    } finally {
      setPending(null);
    }
  }
  const refreshQr = () => command("refresh", "accounts.refresh_qrcode", { ref });
  const logout = (accountId: string) => command("logout", "accounts.logout", { account_id: accountId });
  return { status, error, pending, busy: pending !== null, reload, refreshQr, logout };
}
