import { Eye, EyeSlash } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { iconButtonClass, inputClass, useAccountAction, type PluginAccountDetailComponentProps } from "@shiori/plugin-sdk";

type Detail = { app_id: string; has_secret: boolean; secret_reference: string; connected: boolean; identity: string; bot_id: string; bot_name: string };
type Targets = { coverage: "observed_c2c_only"; targets: Array<{ chat_id: string; user_openid: string }> };

/** QQBot-owned application credentials, C2C targets, and connection commands. */
export function QQBotAccountDetail({ account, roleId, onChanged, client, host }: PluginAccountDetailComponentProps) {
  const accountId = account?.id;
  const [appId, setAppId] = useState(account?.platformAccountId ?? "");
  const [secret, setSecret] = useState("");
  const [showSecret, setShowSecret] = useState(false);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [targets, setTargets] = useState<Targets | null>(null);
  const { pending, busy, error, errorDetail, reportError, run } = useAccountAction(onChanged);

  useEffect(() => {
    if (!accountId) return;
    let active = true;
    void Promise.all([
      client.call<Detail>("account.detail", { account_id: accountId }),
      client.call<Targets>("account.targets", { account_id: accountId }),
    ]).then(([nextDetail, nextTargets]) => {
      if (active) { setDetail(nextDetail); setTargets(nextTargets); setAppId(nextDetail.app_id); }
    }).catch((failure: unknown) => { if (active) reportError(failure, "账号信息加载失败"); });
    return () => { active = false; };
  }, [accountId, client, reportError]);

  const save = () => run("connect", async () => {
    const result = await client.call<{ account_id: string }>("account.save", {
      app_id: appId.trim(), client_secret: secret, role_id: roleId,
    });
    setSecret("");
    setDetail((current) => current ? { ...current, connected: true } : current);
    return result.account_id;
  });

  const disconnect = () => run("disconnect", async () => {
    if (!account) return undefined;
    await client.call("account.disconnect", { account_id: account.id });
    setDetail((current) => current ? { ...current, connected: false } : current);
    return undefined;
  });

  return <div className="grid gap-4 text-body-sm">
    <host.ui.AccountStatusCard account={account} pending={pending}
      action={account && detail?.connected
        ? { kind: "disconnect", onClick: () => void disconnect() }
        : { kind: "connect", onClick: () => void save(), disabled: !appId.trim() || (!secret.trim() && !detail?.has_secret) }}>
      <host.ui.Reveal show={Boolean(error)} className="pt-3"><host.ui.InlineError message={error} detail={errorDetail} /></host.ui.Reveal>
    </host.ui.AccountStatusCard>
    <p className="m-0 font-medium text-ink">QQ 官方机器人应用</p>
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
    {account ? <section className="grid gap-2 border-t border-line-soft pt-4" aria-label="已交互 C2C 用户">
      <h3 className="m-0 text-body font-medium text-ink">已交互 C2C 用户</h3>
      <p className="m-0 text-ink-muted">仅包含此应用已处理消息的用户 OpenID</p>
      {targets?.targets.length ? <ul className="m-0 grid list-none gap-1 p-0">{targets.targets.map((target) => <li key={target.chat_id} className="break-all font-mono text-ink-secondary">{target.user_openid}</li>)}</ul> : <p className="m-0 text-ink-muted">暂无目标</p>}
    </section> : null}
  </div>;
}
