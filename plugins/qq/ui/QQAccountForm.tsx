import { FloppyDiskIcon, PlugIcon } from "@phosphor-icons/react";
import React from "react";
import type { PluginAccountDetailComponentProps } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { ghostButtonClass, inputClass, primaryButtonClass } from "../../../apps/desktop/renderer/src/shared/styles";
import type { useQQAccountForm } from "./useQQAccountForm";

/** QQ-only fields and connection commands inside the host account detail. */
export function QQAccountForm({ account, host, form }: Pick<PluginAccountDetailComponentProps, "account" | "host"> & {
  form: ReturnType<typeof useQQAccountForm>;
}) {
  const { fields, setField, hasToken, ref, dirty, busy, loading, error } = form;
  return <div className="grid gap-4" aria-label="QQ 外部连接">
    {error ? <host.ui.InlineError message={error} /> : null}
    {account ? <div className="grid gap-1 text-body-sm text-ink-secondary">
      <span>QQ 号</span><strong className="text-ink">{account.platformAccountId}</strong>
    </div> : null}
    <label className="grid gap-2 text-body-sm text-ink-secondary">
      NapCat WebSocket 地址
      <input className={inputClass} type="url" value={fields.uri} onChange={(event) => setField("uri", event.target.value)} placeholder="ws://localhost:3001" disabled={busy || loading} />
    </label>
    <label className="grid gap-2 text-body-sm text-ink-secondary">
      WebSocket 令牌
      <input className={inputClass} type="password" value={fields.token} onChange={(event) => setField("token", event.target.value)} placeholder={hasToken ? "已保存，留空则保持原值" : "可留空"} disabled={busy || loading || fields.clearToken} autoComplete="new-password" />
    </label>
    {hasToken ? <label className="flex items-center gap-2 text-body-sm text-ink-secondary">
      <input type="checkbox" checked={fields.clearToken} onChange={(event) => setField("clearToken", event.target.checked)} disabled={busy || loading} />清除已保存令牌
    </label> : null}
    <label className="grid gap-2 text-body-sm text-ink-secondary">
      连接超时（秒）
      <input className={inputClass} type="number" min="0.1" step="0.1" value={fields.timeout} onChange={(event) => setField("timeout", event.target.value)} disabled={busy || loading} />
    </label>
    <div className="flex flex-wrap gap-2">
      <button type="button" className={ghostButtonClass} onClick={() => void form.save()} disabled={busy || loading || !dirty || !fields.uri.trim() || !(Number(fields.timeout) > 0)}><FloppyDiskIcon className="mr-2 inline h-4 w-4" />保存</button>
      <button type="button" className={primaryButtonClass} onClick={() => void form.connect()} disabled={busy || loading || dirty || !ref}><PlugIcon className="mr-2 inline h-4 w-4" />连接</button>
      {account ? <button type="button" className={ghostButtonClass} onClick={() => void form.disconnect()} disabled={busy || loading}><PlugIcon className="mr-2 inline h-4 w-4" />断开连接</button> : null}
    </div>
  </div>;
}
