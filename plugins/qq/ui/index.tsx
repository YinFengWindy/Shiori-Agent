import { PlugIcon, FloppyDiskIcon } from "@phosphor-icons/react";
import React, { useEffect, useState } from "react";
import type { PluginAccountDetailComponentProps, PluginUiModule } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { ghostButtonClass, inputClass, primaryButtonClass } from "../../../apps/desktop/renderer/src/shared/styles";
import { QQDraftsSection } from "./QQDraftsSection";

type ConnectionSettings = {
  ref: string;
  ws_uri: string;
  expected_uin: string;
  display_name: string;
  timeout_seconds: number;
  has_token: boolean;
};

/** QQ-specific external NapCat controls inside the shared account detail. */
export function QQAccountDetail({ account, onChanged, client, host, draftRef = "" }: PluginAccountDetailComponentProps & { draftRef?: string }) {
  const accountId = account?.id;
  const [uri, setUri] = useState("");
  const [token, setToken] = useState("");
  const [timeout, setTimeoutValue] = useState("5");
  const [hasToken, setHasToken] = useState(false);
  const [clearToken, setClearToken] = useState(false);
  const [savedRef, setSavedRef] = useState("");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let current = true;
    setError("");
    if (!accountId && !draftRef) {
      setUri(""); setToken(""); setTimeoutValue("5"); setHasToken(false); setClearToken(false); setSavedRef(""); setDirty(false);
      return;
    }
    setLoading(true);
    void client.call<{ account: ConnectionSettings }>("accounts.settings", accountId ? { account_id: accountId } : { ref: draftRef })
      .then(({ account: settings }) => {
        if (!current) return;
        setUri(settings.ws_uri);
        setToken("");
        setTimeoutValue(String(settings.timeout_seconds));
        setHasToken(settings.has_token);
        setClearToken(false);
        setSavedRef(settings.ref);
        setDirty(false);
      })
      .catch((failure: unknown) => { if (current) setError(String(failure)); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [accountId, draftRef, client]);

  async function save() {
    setBusy(true);
    setError("");
    try {
      const result = await client.call<{ ref: string }>("accounts.save", {
        account_id: account?.id ?? "", ref: savedRef || draftRef, ws_uri: uri.trim(), ws_token: token,
        clear_token: clearToken,
        timeout_seconds: Number(timeout),
      });
      setToken("");
      setHasToken(!clearToken && (hasToken || Boolean(token)));
      setClearToken(false);
      setSavedRef(result.ref);
      setDirty(false);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }

  async function connect() {
    setBusy(true);
    setError("");
    try {
      const result = await client.call<{ account_id: string }>("accounts.connect", { ref: savedRef || draftRef });
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
      await client.call("accounts.disconnect", { account_id: account.id });
      onChanged();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }

  return <div className="grid gap-4" aria-label="QQ 外部连接">
    {error ? <host.ui.InlineError message={error} /> : null}
    {account ? <div className="grid gap-1 text-body-sm text-ink-secondary">
      <span>QQ 号</span><strong className="text-ink">{account.platformAccountId}</strong>
    </div> : null}
    <label className="grid gap-2 text-body-sm text-ink-secondary">
      NapCat WebSocket 地址
      <input className={inputClass} type="url" value={uri} onChange={(event) => { setUri(event.target.value); setDirty(true); }} placeholder="ws://localhost:3001" disabled={busy || loading} />
    </label>
    <label className="grid gap-2 text-body-sm text-ink-secondary">
      WebSocket 令牌
      <input className={inputClass} type="password" value={token} onChange={(event) => { setToken(event.target.value); setDirty(true); }} placeholder={hasToken ? "已保存，留空则保持原值" : "可留空"} disabled={busy || loading} autoComplete="new-password" />
    </label>
    {hasToken ? <label className="flex items-center gap-2 text-body-sm text-ink-secondary">
      <input type="checkbox" checked={clearToken} onChange={(event) => { setClearToken(event.target.checked); setDirty(true); }} disabled={busy || loading} />清除已保存令牌
    </label> : null}
    <label className="grid gap-2 text-body-sm text-ink-secondary">
      连接超时（秒）
      <input className={inputClass} type="number" min="0.1" step="0.1" value={timeout} onChange={(event) => { setTimeoutValue(event.target.value); setDirty(true); }} disabled={busy || loading} />
    </label>
    <div className="flex flex-wrap gap-2">
      <button type="button" className={ghostButtonClass} onClick={() => void save()} disabled={busy || loading || !dirty || !uri.trim() || !(Number(timeout) > 0)}><FloppyDiskIcon className="mr-2 inline h-4 w-4" />保存</button>
      <button type="button" className={primaryButtonClass} onClick={() => void connect()} disabled={busy || loading || dirty || !savedRef}><PlugIcon className="mr-2 inline h-4 w-4" />连接</button>
      {account ? <button type="button" className={ghostButtonClass} onClick={() => void disconnect()} disabled={busy || loading}><PlugIcon className="mr-2 inline h-4 w-4" />断开连接</button> : null}
    </div>
  </div>;
}

const qqUiModule: PluginUiModule = {
  pluginId: "qq",
  // The host appends PluginAccountsSection to this settings slot. The legacy
  // schema remains registered for migration, but its autosave form is hidden.
  settingsSection: { kind: "component", label: "QQ", component: (props) => <QQDraftsSection {...props} Editor={QQAccountDetail} /> },
  accountDetail: { component: QQAccountDetail },
};
export default qqUiModule;
