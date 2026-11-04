import { useId, useState, type FormEvent } from "react";
import { compactGhostButtonClass, settingsInputClass, settingsGroupStackClass, SettingsGroup, SettingsField, Select } from "@yinfengwindy/shiori-sdk";
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
  const [cwd, setCwd] = useState(server?.transport.cwd ?? "");
  const [enabled, setEnabled] = useState(server?.enabled ?? true);
  const [commandEdit, setCommandEdit] = useState<Edit>(server ? "keep" : "replace");
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
    try {
      if (commandEdit === "replace") {
        commandValue = JSON.parse(command);
        if (!Array.isArray(commandValue) || commandValue.length === 0 || !commandValue.every((part) => typeof part === "string" && part.length > 0)) throw new Error();
      }
      if (envEdit === "replace") {
        envValue = JSON.parse(env);
        if (!envValue || Array.isArray(envValue) || typeof envValue !== "object" || !Object.values(envValue).every((value) => typeof value === "string")) throw new Error();
      }
    } catch {
      setError("命令需为 JSON 字符串数组，环境变量需为 JSON 字符串对象");
      form.querySelector<HTMLInputElement>('input[type="password"]:enabled')?.focus();
      return;
    }
    const saved = await save({
      server_id: id, expected_revision: server?.revision,
      config: { label: label || id, enabled, transport: { kind: "stdio", cwd: cwd || null }, tools: { mode, names } },
      credentials: {
        command: commandEdit === "replace" ? { op: "replace", value: commandValue } : { op: commandEdit },
        env: envEdit === "replace" ? { op: "replace", value: envValue } : { op: envEdit },
      },
    });
    if (saved) { setCommand(""); setEnv(""); cancel(); }
  };
  return <form className={settingsGroupStackClass} onSubmit={(event) => { void submit(event); }}>
    <SettingsGroup title={server ? "编辑服务器" : "添加服务器"}>
      <SettingsField label="服务器 ID"><input aria-label="服务器 ID" className={settingsInputClass} value={id} disabled={!!server} required pattern="[a-zA-Z0-9_-]{1,40}" onChange={(event) => setId(event.target.value)} /></SettingsField>
      <SettingsField label="显示名称"><input aria-label="显示名称" className={settingsInputClass} value={label} onChange={(event) => setLabel(event.target.value)} /></SettingsField>
      <SettingsField label="工作目录"><input aria-label="工作目录" className={settingsInputClass} value={cwd} onChange={(event) => setCwd(event.target.value)} /></SettingsField>
      <SettingsField label="启动命令">
        <div className="grid gap-2">
          {server ? <Select aria-label="启动命令编辑方式" value={commandEdit} options={edits.filter((item) => item.value !== "delete")} onValueChange={(value) => setCommandEdit(value === "replace" ? "replace" : "keep")} /> : null}
          {commandEdit === "replace" ? <input type="password" autoComplete="new-password" aria-label="启动命令 JSON" aria-describedby={error ? `${prefix}-error` : undefined} aria-invalid={!!error} required className={settingsInputClass} value={command} placeholder='["npx", "-y", "server-package"]' onChange={(event) => setCommand(event.target.value)} /> : <span className="text-body-sm text-ink-muted">已保存</span>}
        </div>
      </SettingsField>
      <SettingsField label="环境变量">
        <div className="grid gap-2">
          <Select aria-label="环境变量编辑方式" value={envEdit} options={edits} onValueChange={(value) => setEnvEdit(value === "replace" || value === "delete" ? value : "keep")} />
          {envEdit === "replace" ? <input type="password" autoComplete="new-password" aria-label="环境变量 JSON" className={settingsInputClass} value={env} required placeholder='{"API_KEY":"…"}' onChange={(event) => setEnv(event.target.value)} /> : <span className="text-body-sm text-ink-muted">{envEdit === "delete" ? "保存后清空" : server?.env_names.join("、") || "无"}</span>}
        </div>
      </SettingsField>
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
