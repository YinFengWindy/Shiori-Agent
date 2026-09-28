import { ArrowClockwiseIcon, PlugIcon, SignOutIcon, StopIcon } from "@phosphor-icons/react";
import React from "react";
import type { PluginAccountDetailComponentProps } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { compactButtonSizeClass, cx, ghostButtonClass, ghostButtonSurfaceClass, primaryButtonClass } from "../../../apps/desktop/renderer/src/shared/styles";
import type { useQQAccountForm } from "./useQQAccountForm";
import { useManagedNapCat } from "./useManagedNapCat";
import { managedQQStatus } from "./qqStatusPresentation";

const preparationLabels = {
  idle: "等待启动", downloading: "下载中", extracting: "解压中",
  verifying: "校验中", ready: "已就绪", error: "准备失败",
} as const;
const statusTones = {
  success: "bg-success-soft text-success-text",
  accent: "bg-accent-soft text-accent-text",
  muted: "bg-surface-soft text-ink-muted",
  danger: "bg-danger-soft text-danger-text",
} as const;

/** Managed NapCat login and connection controls inside the host account detail. */
export function QQAccountForm({ account, host, form }: Pick<PluginAccountDetailComponentProps, "account" | "host"> & {
  form: ReturnType<typeof useQQAccountForm>;
}) {
  const { ref, busy, loading, error, managedAvailable } = form;
  const managed = useManagedNapCat(form.client, ref, Boolean(ref), account ? undefined : form.onVerified);
  const status = managed.status;
  const preparation = status?.preparation;
  const preparing = preparation?.stage === "downloading" || preparation?.stage === "extracting" || preparation?.stage === "verifying";
  const qr = status?.connection !== "online" ? status?.login.qrcode : "";
  const state = status ? managedQQStatus(status) : null;
  const accountRunning = account?.connection === "online" || account?.connection === "connecting";
  const showStart = managedAvailable && !accountRunning && !preparing
    && (!ref || status?.login.phase === "stopped" || status?.connection === "error" || Boolean(managed.error || error));
  const canStop = Boolean(ref && status && status.login.phase !== "stopped" && status.connection !== "offline");

  return <div className="grid gap-4" aria-label="QQ 连接">
    {error ? <host.ui.InlineError message={error} /> : null}
    {managed.error ? <host.ui.InlineError message={managed.error} /> : null}
    {!managedAvailable && !loading ? <host.ui.InlineError message="托管 NapCat 仅支持 Windows x64" /> : null}
    {account ? <p className="m-0 text-body-sm text-ink-secondary">QQ 号 · <strong className="text-ink">{account.platformAccountId}</strong></p> : null}
    {status ? <div className="grid gap-3 text-body-sm text-ink-secondary" aria-live="polite">
      <div className="flex flex-wrap items-center gap-2">
        <span className={cx("inline-flex items-center rounded-full px-2.5 py-0.5 text-caption", statusTones[state!.tone])}>{state!.label}</span>
        <span className="text-ink-muted">NapCat {preparation!.version}
          {preparation!.stage !== "ready" ? ` · ${preparationLabels[preparation!.stage]}` : ""}
          {preparation!.stage === "downloading" || preparation!.stage === "extracting" ? ` ${preparation!.percent}%` : ""}</span>
      </div>
      {preparing ? <progress className="h-1.5 w-full" max={100} value={preparation!.percent} aria-label="NapCat 准备进度" /> : null}
      {preparation!.error ? <host.ui.InlineError message={preparation!.error} /> : null}
      {status.connection === "error" && status.error ? <host.ui.InlineError message={status.error} /> : null}
      {qr ? <div className="grid justify-items-start gap-3">
        <img src={qr} alt="QQ 登录二维码" className="h-48 w-48 object-contain" />
        <button type="button" className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)}
          onClick={() => void managed.refreshQr()} disabled={managed.busy} title="刷新二维码">
          <ArrowClockwiseIcon className="h-4 w-4" />刷新二维码
        </button>
      </div> : null}
    </div> : ref && !loading ? <span className="text-body-sm text-ink-muted">正在读取 QQ 连接状态</span> : null}
    <div className="flex flex-wrap gap-2">
      {showStart ? <button type="button" className={primaryButtonClass} onClick={() => void form.start().then(() => managed.reload())}
        disabled={busy || loading}><PlugIcon className="mr-2 inline h-4 w-4" />连接</button> : null}
      {canStop ? <button type="button" className={ghostButtonClass} onClick={() => void form.disconnect()}
        disabled={busy || loading}><StopIcon className="mr-2 inline h-4 w-4" />停止</button> : null}
      {account?.connection === "online" ? <button type="button" className={ghostButtonClass}
        onClick={() => void managed.logout(account.id)} disabled={busy || loading || managed.busy}>
        <SignOutIcon className="mr-2 inline h-4 w-4" />退出登录</button> : null}
    </div>
  </div>;
}
