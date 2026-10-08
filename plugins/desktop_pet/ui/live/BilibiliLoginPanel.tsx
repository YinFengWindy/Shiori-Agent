import { compactButtonSizeClass, compactGhostButtonClass, cx, primaryButtonSurfaceClass, usePluginHostServices } from "@yinfengwindy/shiori-sdk";
import type { BilibiliScanState } from "./liveContracts";
import type { BilibiliAccountController } from "./useBilibiliAccount";

const scanLabels: Record<BilibiliScanState, string> = {
  waiting_scan: "等待扫码",
  waiting_confirm: "已扫码，等待确认",
  expired: "二维码已过期",
};

const primaryCompactClass = cx(primaryButtonSurfaceClass, compactButtonSizeClass);

/**
 * The role's Bilibili account and its QR login, shown in place (no further
 * dialog). An invalid login keeps its account visible next to a rescan.
 */
export function BilibiliLoginPanel({ login, disabled }: { login: BilibiliAccountController; disabled: boolean }) {
  const host = usePluginHostServices();
  const { account, qr, error, busy } = login;
  const locked = disabled || busy;
  const scanButton = (label: string) => <button type="button" className={primaryCompactClass} disabled={locked} onClick={() => { void login.startLogin(); }}>{label}</button>;
  return <div className="grid gap-3" data-testid="bilibili-login">
    {error ? <host.ui.InlineError message={error} actions={account === null ? <button type="button" className={compactGhostButtonClass} onClick={login.reload}>重试</button> : undefined} /> : null}
    {account === null && !error ? <span className="text-body-sm text-ink-muted">读取中…</span> : null}
    {account ? <div className="flex flex-wrap items-center gap-2">
      {account.state === "logged_out" ? null : <span className="text-body-sm text-ink" data-testid="bilibili-account">{account.account.uname}（{account.account.uid}）</span>}
      {account.state === "invalid" ? <span className="text-body-sm text-warning-text">登录已失效</span> : null}
      <span className="flex-1" />
      {qr ? null : account.state === "logged_in" ? null : scanButton(account.state === "invalid" ? "重新扫码" : "扫码登录")}
      {account.state === "logged_out" ? null : <button type="button" className={compactGhostButtonClass} disabled={locked} onClick={() => { void login.logout(); }}>退出登录</button>}
    </div> : null}
    {qr ? <div className="flex flex-wrap items-center gap-4">
      <img src={qr.qrcode} alt="B 站登录二维码" className={cx("h-40 w-40 rounded-md border border-line-soft bg-surface", qr.scan === "expired" && "opacity-40")} />
      <div className="grid justify-items-start gap-2">
        <span className="text-body-sm text-ink-secondary" role="status">{scanLabels[qr.scan]}</span>
        {qr.scan === "expired" ? scanButton("刷新二维码") : null}
        <button type="button" className={compactGhostButtonClass} onClick={login.cancelLogin}>取消</button>
      </div>
    </div> : null}
  </div>;
}
