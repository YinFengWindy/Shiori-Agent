import { useEffect, useState } from "react";
import type { PluginAccountDetailComponentProps } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { createPluginBridgeClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { createAccountClient } from "../../../apps/desktop/renderer/src/accounts/accountClient";
import { InlineError } from "../../../apps/desktop/renderer/src/shared/feedback/InlineError";
import { inputClass, primaryButtonClass } from "../../../apps/desktop/renderer/src/shared/styles";
import { Select } from "../../../apps/desktop/renderer/src/shared/ui/Select";
import { configuredApps, withSavedApp, type FeishuApp } from "./accountConfig";

const settings = createPluginBridgeClient();
const accounts = createAccountClient();

/** Plugin-owned credentials and observed private targets in the shared account detail. */
export function FeishuAccountDetail({ account, onChanged, client }: PluginAccountDetailComponentProps) {
  const accountRef = account?.platformAccountId;
  const [values, setValues] = useState<Record<string, unknown> | null>(null);
  const [domain, setDomain] = useState<FeishuApp["domain"]>("feishu");
  const [appId, setAppId] = useState("");
  const [secret, setSecret] = useState("");
  const [profile, setProfile] = useState<{ identity: { open_id?: string }; targets: Array<{ chat_id: string; open_id: string }> } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void settings.getConfig("feishu").then(({ values: saved }) => {
      if (!active) return;
      setValues(saved);
      const selected = configuredApps(saved).find((item) => `${item.domain}:${item.app_id}` === accountRef);
      if (selected) { setDomain(selected.domain); setAppId(selected.app_id); }
    }).catch((failure) => { if (active) setError(String(failure)); });
    return () => { active = false; };
  }, [accountRef]);

  useEffect(() => {
    if (!accountRef) return;
    let active = true;
    void client.call<{ identity: { open_id?: string }; targets: Array<{ chat_id: string; open_id: string }> }>(
      "accounts.profile", { ref: accountRef },
    ).then((result) => { if (active) setProfile(result); })
      .catch((failure) => { if (active) setError(String(failure)); });
    return () => { active = false; };
  }, [accountRef, client]);

  async function save() {
    if (!values || !appId.trim()) return;
    setBusy(true);
    setError("");
    try {
      const latest = (await settings.getConfig("feishu")).values;
      const current = configuredApps(latest).find((item) => `${item.domain}:${item.app_id}` === `${domain}:${appId.trim()}`);
      const appSecret = secret.trim() || current?.app_secret || "";
      if (!appSecret) throw new Error("请输入 App Secret");
      if (!current || secret.trim()) {
        await client.call("accounts.verify", { domain, app_id: appId.trim(), app_secret: appSecret });
      }
      await settings.setConfig("feishu", withSavedApp(latest, { domain, app_id: appId.trim(), app_secret: appSecret }), {
        operationId: crypto.randomUUID(),
      });
      setSecret("");
      const refreshed = await accounts.list();
      onChanged(refreshed.find((item) => item.pluginId === "feishu" && item.platformAccountId === `${domain}:${appId.trim()}`)?.id);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }

  return <div className="grid gap-4">
    {error ? <InlineError message={error} /> : null}
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
    <button type="button" className={primaryButtonClass} disabled={busy || !values || !appId.trim()} onClick={() => void save()}>保存并连接</button>
    {profile?.identity.open_id ? <p className="m-0 break-all text-body-sm text-ink-muted">机器人 open_id（本应用） · {profile.identity.open_id}</p> : null}
    {profile?.targets.length ? <div className="grid gap-2 border-t border-line-soft pt-4 text-body-sm">
      <h3 className="m-0 font-medium text-ink">已交互私聊（本应用）</h3>
      <ul className="m-0 grid gap-1 p-0 text-ink-muted">{profile.targets.map((target) => <li key={target.chat_id} className="list-none break-all">{target.chat_id} · {target.open_id}</li>)}</ul>
    </div> : null}
  </div>;
}
