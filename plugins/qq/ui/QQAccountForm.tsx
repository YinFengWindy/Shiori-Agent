import { ArrowClockwiseIcon, SignOutIcon } from "@phosphor-icons/react";
import React, { useEffect, useRef } from "react";
import { accountOnline, compactGhostButtonClass, useLatestRef, type PluginAccountDetailComponentProps } from "@yinfengwindy/shiori-sdk";
import type { useQQAccountForm } from "./useQQAccountForm";
import { useManagedNapCat } from "./useManagedNapCat";
import { managedLoginOnline, managedQQStatus, napCatDetail, napCatPreparing } from "./qqStatusPresentation";

/** Managed NapCat login and connection controls inside the host account detail. */
export function QQAccountForm({ account, host, form }: Pick<PluginAccountDetailComponentProps, "account" | "host"> & {
  form: ReturnType<typeof useQQAccountForm>;
}) {
  const { ref, loading, error, managedAvailable } = form;
  const managed = useManagedNapCat(form.client, ref, Boolean(ref), account ? undefined : form.onVerified);
  const status = managed.status;
  // A verified login is an account already, even before the host list has caught up.
  const accountId = account?.id || status?.account_id || "";
  const hostOnline = accountOnline(account);
  const pending = form.pending ?? (managed.pending === "logout" ? "logout" : null);
  const preparing = status ? napCatPreparing(status) : false;
  const qr = status && !managedLoginOnline(status) ? status.login.qrcode : "";
  const running = account?.connection === "online" || account?.connection === "connecting" || Boolean(ref && status
    && status.login.phase !== "stopped" && status.connection !== "offline" && status.connection !== "error");
  const statusError = status?.connection === "error" && status.error !== account?.error ? status.error : "";
  const errors = [!managedAvailable && !loading && !error ? "托管 NapCat 仅支持 Windows x64" : "",
    status?.preparation.error ?? "", statusError].filter(Boolean);
  const connect = () => form.start(managed.reload);
  const latestConnect = useLatestRef(connect);
  const autoStarted = useRef(false);
  const adding = !account;

  useEffect(() => {
    // Adding an account opens straight into the QR login. The once-guard lives
    // in a ref so no effect re-run (StrictMode replay, settings reload) opens a
    // second temporary login; a failure leaves the 连接 button as the retry.
    if (!adding || autoStarted.current || loading || !managedAvailable) return;
    autoStarted.current = true;
    void latestConnect.current();
  }, [adding, loading, managedAvailable, latestConnect]);

  return <>
    <host.ui.AccountStatusCard account={account} pending={pending}
      status={status ? managedQQStatus(status, hostOnline) : undefined}
      detail={napCatDetail(status)}
      action={running
        ? { kind: "disconnect", onClick: () => void form.disconnect(accountId, managed.reload), disabled: loading }
        : { kind: "connect", onClick: () => void connect(), disabled: loading || !managedAvailable || preparing }}>
      <host.ui.Reveal show={Boolean(error || managed.error || errors.length)} className="grid gap-2 pt-3">
        {error ? <host.ui.InlineError {...error} /> : null}
        {managed.error ? <host.ui.InlineError {...managed.error} /> : null}
        {errors.map((message) => <host.ui.InlineError key={message} message={message} />)}
      </host.ui.Reveal>
      <host.ui.Reveal show={preparing} className="pt-3">
        <progress className="h-1.5 w-full" max={100} value={status?.preparation.percent ?? 0} aria-label="NapCat 准备进度" />
      </host.ui.Reveal>
      <host.ui.Reveal show={Boolean(qr)} className="grid justify-items-start gap-3 pt-3">
        <img src={qr || undefined} alt="QQ 登录二维码" className="h-48 w-48 object-contain" />
        <button type="button" className={compactGhostButtonClass}
          onClick={() => void managed.refreshQr()} disabled={managed.busy} title="刷新二维码">
          <ArrowClockwiseIcon className="h-4 w-4" />刷新二维码
        </button>
      </host.ui.Reveal>
    </host.ui.AccountStatusCard>
    <host.ui.AccountDetailActions actions={hostOnline && accountId ? [{
      label: "退出登录", icon: SignOutIcon, onClick: () => void managed.logout(accountId),
      pending: managed.pending === "logout", disabled: Boolean(pending) || loading,
    }] : []} />
  </>;
}
