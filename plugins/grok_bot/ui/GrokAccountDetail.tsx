import { useEffect, useState } from "react";
import { ghostButtonClass, inputClass, useAccountAction, type PluginAccountDetailComponentProps } from "@yinfengwindy/shiori-sdk";

type ConnectionDetail = {
  webhook_url: string;
  has_key: boolean;
  enabled: boolean;
  verified: boolean;
  max_messages: number;
  exchange_count: number;
  last_status: string;
  client_path: string;
  connection_file: string;
};

/** Isolate drafts when the account page switches between roles. */
export function GrokAccountDetail(props: PluginAccountDetailComponentProps) {
  return <ConnectionLoader key={`${props.roleId}:${props.account?.id ?? "new"}`} {...props} />;
}

function ConnectionLoader(props: PluginAccountDetailComponentProps) {
  const { account, client, host } = props;
  const [detail, setDetail] = useState<ConnectionDetail | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const accountId = account?.id;
  const connection = account?.connection;
  useEffect(() => {
    if (!accountId) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function refresh() {
      try {
        const value = await client.call<ConnectionDetail>("account.detail", { account_id: accountId });
        if (active) { setDetail(value); setError(""); }
      } catch {
        if (active) setError("连接信息加载失败");
      } finally {
        if (active) timer = setTimeout(() => { void refresh(); }, 5000);
      }
    }
    void refresh();
    return () => { active = false; clearTimeout(timer); };
  }, [accountId, connection, client, revision]);
  if (accountId && !detail) return error
    ? <host.ui.InlineError message={error} />
    : <host.ui.AccountStatusCard account={account} pending={null} />;
  return <><ConnectionForm {...props} detail={detail} onChanged={(id) => {
    setRevision((value) => value + 1);
    props.onChanged(id);
  }} />{error ? <host.ui.InlineError message={error} /> : null}</>;
}

function ConnectionForm({ account, roleId, client, host, onChanged, detail }: PluginAccountDetailComponentProps & { detail: ConnectionDetail | null }) {
  const [webhook, setWebhook] = useState(detail?.webhook_url ?? "");
  const [secret, setSecret] = useState("");
  const [limit, setLimit] = useState(detail?.max_messages ?? 12);
  const { pending, busy, error, errorDetail, run } = useAccountAction(onChanged);
  const connected = account?.connection === "online" || account?.connection === "connecting";
  const canSave = Boolean(webhook.trim() && (secret.trim() || detail?.has_key)) && limit >= 2 && limit <= 100;

  async function save() {
    const ok = await run("connect", async () => {
      const result = await client.call<{ account_id: string }>("account.save", {
        role_id: roleId, ...(account ? { account_id: account.id } : {}),
        webhook_url: webhook.trim(), max_messages: limit,
        ...(secret.trim() ? { webhook_key: secret.trim() } : {}),
      });
      return result.account_id;
    });
    if (ok) setSecret("");
  }

  async function disconnect() {
    if (!account) return;
    await run("disconnect", async () => {
      await client.call("account.disconnect", { account_id: account.id, role_id: roleId });
      return account.id;
    });
  }

  async function continueExchange() {
    if (!account) return;
    await run("connect", async () => {
      await client.call("account.reset_exchange", { account_id: account.id, role_id: roleId });
      return account.id;
    });
  }

  return <div className="grid gap-4">
    <host.ui.AccountStatusCard account={account} pending={pending} action={connected
      ? { kind: "disconnect", onClick: () => void disconnect() }
      : { kind: "connect", onClick: () => void save(), disabled: !canSave }}>
      <host.ui.Reveal show={Boolean(error)} className="pt-3">
        {error ? <host.ui.InlineError message={error} detail={errorDetail} /> : null}
      </host.ui.Reveal>
    </host.ui.AccountStatusCard>
    <label className="grid gap-2 text-body-sm text-ink-secondary">Webhook
      <input className={inputClass} type="url" value={webhook} disabled={busy || connected} onChange={(event) => setWebhook(event.target.value)} autoComplete="off" />
    </label>
    <label className="grid gap-2 text-body-sm text-ink-secondary">Webhook 密钥
      <input className={inputClass} type="password" value={secret} disabled={busy || connected} onChange={(event) => setSecret(event.target.value)} autoComplete="new-password" placeholder={detail?.has_key ? "已保存" : ""} />
    </label>
    <label className="grid gap-2 text-body-sm text-ink-secondary">连续交流消息上限
      <input className={inputClass} type="number" min={2} max={100} value={limit} disabled={busy || connected} onChange={(event) => setLimit(Number(event.target.value))} />
    </label>
    {detail ? <div className="grid gap-2 border-t border-line-soft pt-4 text-body-sm text-ink-secondary">
      <span>{detail.verified ? "回程已验证" : "等待回程验证"} · {detail.exchange_count} / {detail.max_messages}</span>
      {detail.last_status ? <span role="status">{detail.last_status}</span> : null}
      <button className={ghostButtonClass} disabled={busy || !connected} onClick={() => void continueExchange()}>继续新一轮交流</button>
      <details><summary>回程客户端</summary>
        <dl className="grid gap-2 text-ink-muted"><dt>客户端</dt><dd className="m-0 break-all">{detail.client_path}</dd><dt>连接文件</dt><dd className="m-0 break-all">{detail.connection_file}</dd></dl>
      </details>
    </div> : null}
  </div>;
}
