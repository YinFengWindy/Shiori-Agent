import { useState } from "react";
import { settingsInputClass, SettingsField, Select } from "@yinfengwindy/shiori-sdk";

type Client = { client_id: string | null; client_secret: string | null; auth_method: "none" | "client_secret_basic" | "client_secret_post"; redirect_port: number };
/** Explicit replacement of private pre-registration settings. */
export type OAuthClientEdit = { op: "keep" | "delete" } | { op: "replace"; value: Client };

/** Keep existing client secrets out of the read projection and editor. */
export function OAuthClientEditor({ configured, onChange }: { configured: boolean; onChange: (edit: OAuthClientEdit) => void }) {
  const [mode, setMode] = useState("keep");
  const [value, setValue] = useState<Client>({ client_id: null, client_secret: null, auth_method: "none", redirect_port: 43819 });
  const update = (patch: Partial<Client>) => { const next = { ...value, ...patch }; setValue(next); onChange({ op: "replace", value: next }); };
  return <>
    <SettingsField label="OAuth 客户端"><Select aria-label="OAuth 客户端" value={mode} options={[{ value: "keep", label: configured ? "保留客户端" : "自动注册" }, { value: "replace", label: "配置客户端" }, { value: "delete", label: "重置为自动注册" }]} onValueChange={(next) => { setMode(next); onChange(next === "replace" ? { op: "replace", value } : { op: next === "delete" ? "delete" : "keep" }); }} /></SettingsField>
    {mode === "replace" ? <>
      <SettingsField label="Client ID"><input aria-label="Client ID" autoComplete="off" className={settingsInputClass} value={value.client_id ?? ""} onChange={(event) => update({ client_id: event.target.value || null })} /></SettingsField>
      <SettingsField label="Client secret"><input aria-label="Client secret" type="password" autoComplete="new-password" className={settingsInputClass} value={value.client_secret ?? ""} onChange={(event) => update({ client_secret: event.target.value || null })} /></SettingsField>
      <SettingsField label="客户端认证"><Select aria-label="客户端认证" value={value.auth_method} options={[{ value: "none", label: "none" }, { value: "client_secret_basic", label: "client_secret_basic" }, { value: "client_secret_post", label: "client_secret_post" }]} onValueChange={(next) => update({ auth_method: next === "client_secret_basic" || next === "client_secret_post" ? next : "none" })} /></SettingsField>
      <SettingsField label="回调端口"><input aria-label="回调端口" type="number" min={1024} max={65535} required className={settingsInputClass} value={value.redirect_port} onChange={(event) => update({ redirect_port: Number(event.target.value) })} /></SettingsField>
      <SettingsField label="回调地址"><span className="break-all text-body-sm text-ink-muted">http://127.0.0.1:{value.redirect_port}/callback</span></SettingsField>
    </> : null}
  </>;
}
