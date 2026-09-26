import { Eye, EyeSlash } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import type { PluginAccountDetailComponentProps } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { ghostButtonClass, iconButtonClass, inputClass, primaryButtonClass } from "../../../apps/desktop/renderer/src/shared/styles";

type Detail = { app_id: string; has_secret: boolean; secret_reference: string; connected: boolean; identity: string; bot_id: string; bot_name: string };
type Targets = { coverage: "observed_c2c_only"; targets: Array<{ chat_id: string; user_openid: string }> };

/** QQBot-owned application credentials, C2C targets, and connection commands. */
export function QQBotAccountDetail({ account, onChanged, client }: PluginAccountDetailComponentProps) {
  const accountId = account?.id;
  const [appId, setAppId] = useState(account?.platformAccountId ?? "");
  const [secret, setSecret] = useState("");
  const [showSecret, setShowSecret] = useState(false);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [targets, setTargets] = useState<Targets | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!accountId) return;
    let active = true;
    void Promise.all([
      client.call<Detail>("account.detail", { account_id: accountId }),
      client.call<Targets>("account.targets", { account_id: accountId }),
    ]).then(([nextDetail, nextTargets]) => {
      if (active) { setDetail(nextDetail); setTargets(nextTargets); setAppId(nextDetail.app_id); }
    }).catch((failure: unknown) => { if (active) setError(String(failure)); });
    return () => { active = false; };
  }, [accountId, client]);

  async function save() {
    setBusy(true);
    setError("");
    try {
      const result = await client.call<{ account_id: string }>("account.save", {
        app_id: appId.trim(), client_secret: secret,
      });
      setSecret("");
      onChanged(result.account_id);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    if (!account) return;
    setBusy(true);
    setError("");
    try {
      await client.call("account.disconnect", { account_id: account.id });
      setDetail((current) => current ? { ...current, connected: false } : current);
      onChanged();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }

  return <div className="grid gap-4 text-body-sm">
    <div className="grid gap-1">
      <p className="m-0 font-medium text-ink">QQ 官方机器人应用</p>
      {detail?.bot_name ? <p className="m-0 text-ink-muted">{detail.bot_name}</p> : null}
      {detail?.bot_id ? <p className="m-0 break-all text-ink-muted">Bot ID {detail.bot_id}</p> : null}
    </div>
    <label className="grid gap-2 text-ink-secondary">App ID
      <input className={inputClass} value={appId} disabled={busy || Boolean(account)} onChange={(event) => setAppId(event.target.value)} autoComplete="off" />
    </label>
    <label className="grid gap-2 text-ink-secondary">App Secret
      <span className="flex items-center gap-2">
        <input className={inputClass} type={showSecret ? "text" : "password"} value={secret} disabled={busy} onChange={(event) => setSecret(event.target.value)} placeholder={detail?.secret_reference || (detail?.has_secret ? "已保存" : "")} autoComplete="new-password" />
        <button type="button" className={iconButtonClass} title={showSecret ? "隐藏密钥" : "显示密钥"} aria-label={showSecret ? "隐藏密钥" : "显示密钥"} onClick={() => setShowSecret((value) => !value)}>
          {showSecret ? <EyeSlash className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
        </button>
      </span>
    </label>
    {error ? <p role="alert" className="m-0 break-words text-danger-text">{error}</p> : null}
    <div className="flex flex-wrap gap-2">
      <button type="button" className={primaryButtonClass} disabled={busy || !appId.trim() || (!secret.trim() && !detail?.has_secret)} onClick={() => void save()}>{busy ? "连接中" : "保存并连接"}</button>
      {account && detail?.connected ? <button type="button" className={ghostButtonClass} disabled={busy} onClick={() => void disconnect()}>断开连接</button> : null}
    </div>
    {account ? <section className="grid gap-2 border-t border-line-soft pt-4" aria-label="已交互 C2C 用户">
      <h3 className="m-0 text-body font-medium text-ink">已交互 C2C 用户</h3>
      <p className="m-0 text-ink-muted">仅包含此应用已处理消息的用户 OpenID</p>
      {targets?.targets.length ? <ul className="m-0 grid list-none gap-1 p-0">{targets.targets.map((target) => <li key={target.chat_id} className="break-all font-mono text-ink-secondary">{target.user_openid}</li>)}</ul> : <p className="m-0 text-ink-muted">暂无目标</p>}
    </section> : null}
  </div>;
}
