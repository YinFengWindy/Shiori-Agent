import { useId, useState, type FormEvent } from "react";
import { compactGhostButtonClass, settingsInputClass, settingsGroupStackClass, SettingsGroup, SettingsField, Select } from "@yinfengwindy/shiori-sdk";
import { OAuthClientEditor, type OAuthClientEdit } from "./OAuthClientEditor";
import type { McpServer } from "./types";

type Edit = "keep" | "replace" | "delete";
const edits = [{ value: "keep", label: "保留" }, { value: "replace", label: "替换" }, { value: "delete", label: "清空" }];

/** A revision-bound form: live status updates never overwrite the user's draft. */
export function ServerEditor({ server, busy, save, cancel }: {
  server: McpServer | null; busy: boolean;
  save: (payload: Record<string, unknown>) => Promise<boolean>; cancel: () => void;
}) {
  const prefix = useId();
  const [id, setId] = useState(server?.id ?? "");
  const [label, setLabel] = useState(server?.label ?? "");
  const [kind, setKind] = useState<"stdio" | "streamable_http">(server?.transport.kind ?? "stdio");
  const [cwd, setCwd] = useState(server?.transport.kind === "stdio" ? server.transport.cwd ?? "" : "");
  const [auth, setAuth] = useState<"none" | "bearer" | "headers" | "oauth">(server?.transport.kind === "streamable_http" ? server.transport.auth : "none");
  const [oauthEdit, setOAuthEdit] = useState<OAuthClientEdit>({ op: "keep" });
  const [urlEdit, setUrlEdit] = useState<Edit>(server?.url_configured ? "keep" : "replace");
  const [url, setUrl] = useState("");
  const [bearerEdit, setBearerEdit] = useState<Edit>(server?.bearer_configured ? "keep" : "replace");
  const [bearer, setBearer] = useState("");
  const [headersEdit, setHeadersEdit] = useState<Edit>("keep");
  const [headers, setHeaders] = useState("");
  const [enabled, setEnabled] = useState(server?.enabled ?? true);
  const [commandEdit, setCommandEdit] = useState<Edit>(server?.command_configured ? "keep" : "replace");
  const [command, setCommand] = useState("");
  const [envEdit, setEnvEdit] = useState<Edit>("keep");
  const [env, setEnv] = useState("");
  const [mode, setMode] = useState<"all" | "selected">(server?.selection.mode ?? "all");
  const [names, setNames] = useState(server?.selection.names ?? []);
  const [error, setError] = useState<string | null>(null);
  const available = [...new Set([...(server?.tools.map((tool) => tool.name) ?? []), ...names])];
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setError(null);
    const form = event.currentTarget;
    let commandValue: unknown;
    let envValue: unknown;
    let headersValue: unknown;
    try {
      if (kind === "stdio" && commandEdit === "replace") {
        commandValue = JSON.parse(command);
        if (!Array.isArray(commandValue) || commandValue.length === 0 || !commandValue.every((part) => typeof part === "string" && part.length > 0)) throw new Error();
      }
      if (kind === "stdio" && envEdit === "replace") {
        envValue = JSON.parse(env);
        if (!envValue || Array.isArray(envValue) || typeof envValue !== "object" || !Object.values(envValue).every((value) => typeof value === "string")) throw new Error();
      }
      if (kind === "streamable_http" && headersEdit === "replace") {
        headersValue = JSON.parse(headers);
        if (!headersValue || Array.isArray(headersValue) || typeof headersValue !== "object" || !Object.values(headersValue).every((value) => typeof value === "string")) throw new Error();
      }
    } catch {
      setError(kind === "stdio" ? "命令需为 JSON 字符串数组，环境变量需为 JSON 字符串对象" : "请求头需为 JSON 字符串对象");
      form.querySelector<HTMLInputElement>('input[type="password"]:enabled')?.focus();
      return;
    }
    const saved = await save({
      server_id: id, expected_revision: server?.revision,
      config: { label: label || id, enabled, transport: kind === "stdio" ? { kind, cwd: cwd || null } : { kind, auth }, tools: { mode, names } },
      credentials: kind === "stdio" ? {
        command: commandEdit === "replace" ? { op: "replace", value: commandValue } : { op: commandEdit },
        env: envEdit === "replace" ? { op: "replace", value: envValue } : { op: envEdit },
      } : {
        oauth: auth === "oauth" ? oauthEdit : { op: "delete" },
        url: urlEdit === "replace" ? { op: "replace", value: url } : { op: urlEdit },
        bearer: auth !== "bearer" ? { op: "delete" } : bearerEdit === "replace" ? { op: "replace", value: bearer } : { op: bearerEdit },
        headers: headersEdit === "replace" ? { op: "replace", value: headersValue } : { op: headersEdit },
      },
    });
    if (saved) { setCommand(""); setEnv(""); setUrl(""); setBearer(""); setHeaders(""); cancel(); }
  };
  return <form className={settingsGroupStackClass} onSubmit={(event) => { void submit(event); }}>
    <SettingsGroup title={server ? "编辑服务器" : "添加服务器"}>
      <SettingsField label="服务器 ID"><input aria-label="服务器 ID" className={settingsInputClass} value={id} disabled={!!server} required pattern="[a-zA-Z0-9_-]{1,40}" onChange={(event) => setId(event.target.value)} /></SettingsField>
      <SettingsField label="显示名称"><input aria-label="显示名称" className={settingsInputClass} value={label} onChange={(event) => setLabel(event.target.value)} /></SettingsField>
      <SettingsField label="连接方式"><Select aria-label="连接方式" value={kind} options={[{ value: "stdio", label: "stdio" }, { value: "streamable_http", label: "Streamable HTTP" }]} onValueChange={(value) => setKind(value === "streamable_http" ? "streamable_http" : "stdio")} /></SettingsField>
      {kind === "stdio" ? <>
      <SettingsField label="工作目录"><input aria-label="工作目录" className={settingsInputClass} value={cwd} onChange={(event) => setCwd(event.target.value)} /></SettingsField>
      <SettingsField label="启动命令">
        <div className="grid gap-2">
          {server ? <Select aria-label="启动命令编辑方式" value={commandEdit} options={edits.filter((item) => item.value !== "delete")} onValueChange={(value) => setCommandEdit(value === "replace" ? "replace" : "keep")} /> : null}
          {commandEdit === "replace" ? <input type="password" autoComplete="new-password" aria-label="启动命令 JSON" aria-describedby={error ? `${prefix}-error` : undefined} aria-invalid={!!error} required className={settingsInputClass} value={command} placeholder='["npx", "-y", "server-package"]' onChange={(event) => setCommand(event.target.value)} /> : <span className="text-body-sm text-ink-muted">已保存</span>}
        </div>
      </SettingsField>
      </> : <>
        <SettingsField label="服务器地址"><div className="grid gap-2">
          {server?.url_configured ? <Select aria-label="服务器地址编辑方式" value={urlEdit} options={edits.filter((item) => item.value !== "delete")} onValueChange={(value) => setUrlEdit(value === "replace" ? "replace" : "keep")} /> : null}
          {urlEdit === "replace" ? <input type="password" autoComplete="new-password" aria-label="服务器地址" className={settingsInputClass} value={url} required placeholder="https://example.com/mcp" onChange={(event) => setUrl(event.target.value)} /> : <span className="text-body-sm text-ink-muted">已保存</span>}
        </div></SettingsField>
        <SettingsField label="认证方式"><Select aria-label="认证方式" value={auth} options={[{ value: "none", label: "无认证" }, { value: "bearer", label: "Bearer" }, { value: "headers", label: "自定义请求头" }, { value: "oauth", label: "OAuth" }]} onValueChange={(value) => setAuth(value === "bearer" || value === "headers" || value === "oauth" ? value : "none")} /></SettingsField>
        {auth === "oauth" ? <OAuthClientEditor configured={!!server?.oauth?.client_configured} onChange={setOAuthEdit} /> : null}
        {auth === "bearer" ? <SettingsField label="Bearer token"><div className="grid gap-2">
          {server?.bearer_configured ? <Select aria-label="Bearer token 编辑方式" value={bearerEdit} options={edits.filter((item) => item.value !== "delete")} onValueChange={(value) => setBearerEdit(value === "replace" ? "replace" : "keep")} /> : null}
          {bearerEdit === "replace" ? <input type="password" autoComplete="new-password" aria-label="Bearer token" className={settingsInputClass} value={bearer} required onChange={(event) => setBearer(event.target.value)} /> : <span className="text-body-sm text-ink-muted">已保存</span>}
        </div></SettingsField> : null}
        <SettingsField label="请求头"><div className="grid gap-2">
          <Select aria-label="请求头编辑方式" value={headersEdit} options={edits} onValueChange={(value) => setHeadersEdit(value === "replace" || value === "delete" ? value : "keep")} />
          {headersEdit === "replace" ? <input type="password" autoComplete="new-password" aria-label="请求头 JSON" className={settingsInputClass} value={headers} required placeholder='{"X-API-Key":"…"}' onChange={(event) => setHeaders(event.target.value)} /> : <span className="text-body-sm text-ink-muted">{headersEdit === "delete" ? "保存后清空" : server?.header_names.join("、") || "无"}</span>}
        </div></SettingsField>
      </>}
      {kind === "stdio" ? <SettingsField label="环境变量">
        <div className="grid gap-2">
          <Select aria-label="环境变量编辑方式" value={envEdit} options={edits} onValueChange={(value) => setEnvEdit(value === "replace" || value === "delete" ? value : "keep")} />
          {envEdit === "replace" ? <input type="password" autoComplete="new-password" aria-label="环境变量 JSON" className={settingsInputClass} value={env} required placeholder='{"API_KEY":"…"}' onChange={(event) => setEnv(event.target.value)} /> : <span className="text-body-sm text-ink-muted">{envEdit === "delete" ? "保存后清空" : server?.env_names.join("、") || "无"}</span>}
        </div>
      </SettingsField> : null}
      <label className="flex min-h-10 items-center gap-2 py-4 text-body-sm"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />启用服务器</label>
    </SettingsGroup>
    <SettingsGroup title="工具">
      <div className="py-4"><Select aria-label="工具选择模式" value={mode} options={[{ value: "all", label: "全部工具" }, { value: "selected", label: "选择工具" }]} onValueChange={(value) => setMode(value === "selected" ? "selected" : "all")} /></div>
      {mode === "selected" ? <div className="grid gap-1">
        {available.map((name) => <label key={name} className="flex min-h-10 items-center gap-2 break-all text-body-sm"><input type="checkbox" checked={names.includes(name)} onChange={(event) => setNames(event.target.checked ? [...names, name] : names.filter((item) => item !== name))} />{name}</label>)}
        {available.length === 0 ? <span className="text-body-sm text-ink-muted">未发现工具</span> : null}
      </div> : null}
    </SettingsGroup>
    <div id={`${prefix}-error`} role="alert" className="text-body-sm text-danger">{error}</div>
    <div className="flex flex-wrap gap-2"><button type="submit" className={compactGhostButtonClass} disabled={busy}>{busy ? "保存中…" : "保存"}</button><button type="button" className={compactGhostButtonClass} onClick={cancel} disabled={busy}>取消</button></div>
  </form>;
}
