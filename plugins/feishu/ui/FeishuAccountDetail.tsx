import { useEffect, useState } from "react";
import type { PluginAccountDetailComponentProps } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { useAccountAction } from "../../../apps/desktop/renderer/src/accounts/useAccountAction";
import { compactGhostButtonClass, compactPrimaryButtonClass, inputClass } from "../../../apps/desktop/renderer/src/shared/styles";
import { Select } from "../../../apps/desktop/renderer/src/shared/ui/Select";

type FeishuDomain = "feishu" | "lark";
type FeishuProfile = { identity: { open_id?: string }; targets: Array<{ chat_id: string; open_id: string }> };

/** Splits an account's `<domain>:<app_id>` platform reference. */
function parseRef(ref: string | undefined): { domain: FeishuDomain; appId: string } | null {
  const [domain, ...rest] = (ref ?? "").split(":");
  return (domain === "feishu" || domain === "lark") && rest.length ? { domain, appId: rest.join(":") } : null;
}

/** Plugin-owned credentials and observed private targets in the shared account detail. */
export function FeishuAccountDetail({ account, roleId, onChanged, client, host }: PluginAccountDetailComponentProps) {
  const accountRef = account?.platformAccountId;
  const saved = parseRef(accountRef);
  const [domain, setDomain] = useState<FeishuDomain>(saved?.domain ?? "feishu");
  const [appId, setAppId] = useState(saved?.appId ?? "");
  const [secret, setSecret] = useState("");
  const [profile, setProfile] = useState<FeishuProfile | null>(null);
  const { busy, error, setError, run } = useAccountAction(onChanged);

  useEffect(() => {
    if (!accountRef) return;
    let active = true;
    void client.call<FeishuProfile>("accounts.profile", { ref: accountRef })
      .then((result) => { if (active) setProfile(result); })
      .catch((failure) => { if (active) setError(String(failure)); });
    return () => { active = false; };
  }, [accountRef, client, setError]);

  async function save() {
    if (!appId.trim()) return;
    const ok = await run(async () => {
      const result = await client.call<{ account_id: string }>("accounts.save", {
        role_id: roleId, domain, app_id: appId.trim(), ...(secret.trim() ? { app_secret: secret.trim() } : {}),
      });
      return result.account_id;
    });
    if (ok) setSecret("");
  }

  async function disconnect() {
    if (!account) return;
    await run(async () => {
      await client.call("accounts.disconnect", { account_id: account.id, role_id: roleId });
      return account.id;
    });
  }

  const connected = account?.connection === "online" || account?.connection === "connecting";
  return <div className="grid gap-4">
    {error ? <host.ui.InlineError message={error} /> : null}
    {account?.connection === "login_required" && account.error ? <host.ui.InlineError message={account.error} /> : null}
    <label className="grid gap-2 text-body-sm text-ink-secondary">区域
      <Select aria-label="区域" value={domain} disabled={busy || Boolean(account)} options={[
        { value: "feishu", label: "飞书" }, { value: "lark", label: "Lark" },
      ]} onValueChange={(value) => setDomain(value === "lark" ? "lark" : "feishu")} />
    </label>
    <label className="grid gap-2 text-body-sm text-ink-secondary">App ID
      <input className={inputClass} value={appId} disabled={busy || Boolean(account)} onChange={(event) => setAppId(event.target.value)} autoComplete="off" />
    </label>
    <label className="grid gap-2 text-body-sm text-ink-secondary">App Secret
      <input className={inputClass} type="password" value={secret} disabled={busy} onChange={(event) => setSecret(event.target.value)} autoComplete="new-password" placeholder={account ? "已保存" : ""} />
    </label>
    <div className="flex flex-wrap gap-2">
      <button type="button" className={compactPrimaryButtonClass} disabled={busy || !appId.trim() || (!account && !secret.trim())} onClick={() => void save()}>连接</button>
      {account ? <button type="button" className={compactGhostButtonClass} disabled={busy} onClick={() => void (connected ? disconnect() : save())}>
        {connected ? "断开连接" : "重新连接"}</button> : null}
    </div>
    {profile?.identity.open_id ? <p className="m-0 break-all text-body-sm text-ink-muted">机器人 open_id（本应用） · {profile.identity.open_id}</p> : null}
    {profile?.targets.length ? <div className="grid gap-2 border-t border-line-soft pt-4 text-body-sm">
      <h3 className="m-0 font-medium text-ink">已交互私聊（本应用）</h3>
      <ul className="m-0 grid gap-1 p-0 text-ink-muted">{profile.targets.map((target) => <li key={target.chat_id} className="list-none break-all">{target.chat_id} · {target.open_id}</li>)}</ul>
    </div> : null}
  </div>;
}
