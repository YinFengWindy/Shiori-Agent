import { useState } from "react";
import { compactGhostButtonClass, cx, Select, SettingsField, SettingsGroup, settingsGroupStackClass, settingsInputClass, usePrivateAutosave, type PluginConfigValues, type PluginSettingsSectionComponentProps, type SelectOption } from "@yinfengwindy/shiori-sdk";
import type { HerdrSession, HerdrSettings } from "./types";
import { useHerdrSessions } from "./useHerdrSessions";

const agentOptions: SelectOption[] = [{ value: "codex", label: "Codex" }, { value: "claude", label: "Claude Code" }];
const modelFields = [["codex_model", "Codex 模型"], ["claude_model", "Claude Code 模型"]] as const;
const timeoutFields = [["cli_timeout_seconds", "CLI 超时（秒）", 5, 300], ["task_timeout_seconds", "任务追踪超时（秒）", 60, 86400]] as const;

/** The stored config with the schema's defaults filled in; any other shape fails the read. */
function herdrSettings(values: PluginConfigValues): HerdrSettings {
  const { executable, session, default_agent, codex_model, claude_model, cli_timeout_seconds, task_timeout_seconds } = values;
  if (typeof executable !== "string" || typeof session !== "string" || (default_agent !== "codex" && default_agent !== "claude")
    || typeof codex_model !== "string" || typeof claude_model !== "string"
    || typeof cli_timeout_seconds !== "number" || typeof task_timeout_seconds !== "number") {
    throw new Error("Herdr 配置格式无效");
  }
  return { executable, session, default_agent, codex_model, claude_model, cli_timeout_seconds, task_timeout_seconds };
}

/** The session picker's choices: listed sessions with their state, plus the configured one when Herdr does not list it. */
export function sessionOptions(sessions: HerdrSession[] | null, current: string): SelectOption[] {
  const options: SelectOption[] = (sessions ?? []).map(({ name, status }) => ({ value: name, label: `${name}（${status === "running" ? "运行中" : "已停止"}）` }));
  if (!options.some((option) => option.value === current)) options.unshift({ value: current, label: sessions ? `${current}（未找到）` : current });
  return options;
}

/**
 * A text field whose value the config schema constrains: valid text moves the
 * draft, invalid text stays on screen (marked) without being saved. Typed text
 * is shown only while it belongs to the stored value it was typed against.
 */
function CheckedInput<T extends string | number>({ label, value, parse, onChange }: { label: string; value: T; parse: (text: string) => T | null; onChange: (value: T) => void }) {
  const [typed, setTyped] = useState<{ text: string; value: T } | null>(null);
  const text = typed && typed.value === value ? typed.text : String(value);
  const invalid = parse(text) === null;
  return <input aria-label={label} aria-invalid={invalid || undefined} className={cx(settingsInputClass, invalid && "border-danger")} value={text}
    onChange={(event) => {
      const next = event.target.value;
      const parsed = parse(next);
      setTyped({ text: next, value: parsed ?? value });
      if (parsed !== null) onChange(parsed);
    }} />;
}

function parseExecutable(text: string) {
  return text.trim() ? text : null;
}

function integerParser(min: number, max: number) {
  return (text: string) => {
    const number = /^\d+$/.test(text.trim()) ? Number(text) : Number.NaN;
    return number >= min && number <= max ? number : null;
  };
}

/** 设置 › 插件 › Herdr: autosaves the plugin config; the session is picked from Herdr's local session list. */
export function HerdrSettingsPage({ client, host }: PluginSettingsSectionComponentProps) {
  const state = usePrivateAutosave<HerdrSettings>(client, "config", {
    load: async () => herdrSettings(await host.config.get()),
    save: async (value) => herdrSettings(await host.config.save(value)),
  });
  const sessions = useHerdrSessions(client);
  const draft = state.draft;
  const set = <K extends keyof HerdrSettings>(field: K, value: HerdrSettings[K]) => state.update((current) => ({ ...current, [field]: value }));
  return <div className={settingsGroupStackClass}>
    <host.ui.SettingsSavedStatus phase={state.savePhase} />
    {state.loadError ? <host.ui.InlineError message={state.loadError} actions={<button type="button" className={compactGhostButtonClass} onClick={state.reload}>重新加载</button>} /> : null}
    {state.saveError ? <host.ui.InlineError message={state.saveError} actions={<button type="button" className={compactGhostButtonClass} onClick={state.retry}>重试</button>} /> : null}
    {!draft && state.loading ? <span className="text-body-sm text-ink-muted">正在读取设置…</span> : null}
    {draft ? <>
      <SettingsGroup title="Herdr">
        <SettingsField label="Herdr 路径">
          <CheckedInput label="Herdr 路径" value={draft.executable} parse={parseExecutable} onChange={(value) => set("executable", value)} />
        </SettingsField>
        <SettingsField label="Session">
          <div className="grid gap-2">
            <Select aria-label="Session" className={settingsInputClass} value={draft.session} options={sessionOptions(sessions.sessions, draft.session)} onValueChange={(value) => set("session", value)} />
            {sessions.error ? <host.ui.InlineError message={`读取 session 列表失败：${sessions.error}`} actions={<button type="button" className={compactGhostButtonClass} onClick={sessions.reload}>重试</button>} /> : null}
          </div>
        </SettingsField>
      </SettingsGroup>
      <SettingsGroup title="Agent">
        <SettingsField label="默认 Agent">
          <Select aria-label="默认 Agent" className={settingsInputClass} value={draft.default_agent} options={agentOptions} onValueChange={(value) => set("default_agent", value === "claude" ? "claude" : "codex")} />
        </SettingsField>
        {modelFields.map(([field, label]) => <SettingsField key={field} label={label}>
          <input aria-label={label} className={settingsInputClass} value={draft[field]} onChange={(event) => set(field, event.target.value)} />
        </SettingsField>)}
      </SettingsGroup>
      <SettingsGroup title="超时">
        {timeoutFields.map(([field, label, min, max]) => <SettingsField key={field} label={label}>
          <CheckedInput label={label} value={draft[field]} parse={integerParser(min, max)} onChange={(value) => set(field, value)} />
        </SettingsField>)}
      </SettingsGroup>
    </> : null}
  </div>;
}
