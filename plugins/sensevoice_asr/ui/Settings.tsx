import { compactGhostButtonClass, cx, ManagedRuntimePanel, Select, SettingsField, SettingsGroup, settingsGroupStackClass, settingsInputClass, usePrivateAutosave, type PluginSettingsSectionComponentProps, type SelectOption } from "@yinfengwindy/shiori-sdk";
import type { SenseVoiceSettings } from "./contract";
import { TranscriptionTest } from "./TranscriptionTest";
import { useServiceHealth } from "./useServiceHealth";

const connectionModeOptions: SelectOption[] = [{ value: "external", label: "外部服务" }, { value: "managed", label: "插件托管" }];
const valueClass = "text-body-sm text-ink-secondary";

/** Autosaves SenseVoice connection edits and reports actual service readiness. */
export function SenseVoiceSettingsPage({ client, host }: PluginSettingsSectionComponentProps) {
  const state = usePrivateAutosave<SenseVoiceSettings>(client, "settings", {
    load: () => client.call<SenseVoiceSettings>("settings.get"),
    save: (value) => client.call<SenseVoiceSettings>("settings.set", value),
  });
  // Health describes the stored endpoint and resets whenever a save lands.
  const connection = useServiceHealth(client, state.saved);
  const draft = state.draft;
  // Service actions act on the stored settings, so they wait while an edit is unsaved or its save failed.
  const unsettled = state.savePhase !== "idle";
  return <div className={settingsGroupStackClass}>
    <host.ui.SettingsSavedStatus phase={state.savePhase} />
    {state.loadError ? <host.ui.InlineError message={state.loadError} actions={<button type="button" className={compactGhostButtonClass} onClick={state.reload}>重新加载</button>} /> : null}
    {state.saveError ? <host.ui.InlineError message={state.saveError} actions={<button type="button" className={compactGhostButtonClass} onClick={state.retry}>重试</button>} /> : null}
    {connection.error ? <host.ui.InlineError message={connection.error} /> : null}
    {!draft && state.loading ? <span className="text-body-sm text-ink-muted">正在读取设置…</span> : null}
    {draft ? <>
      <SettingsGroup title="连接">
        <SettingsField label="连接模式">
          <Select aria-label="连接模式" className={settingsInputClass} value={draft.connection_mode} options={connectionModeOptions} onValueChange={(mode) => state.update((current) => ({ ...current, connection_mode: mode === "managed" ? "managed" : "external" }))} />
        </SettingsField>
        {draft.connection_mode === "external" ? <SettingsField label="服务地址">
          <input aria-label="服务地址" className={settingsInputClass} value={draft.url} onChange={(event) => { const url = event.target.value; state.update((current) => ({ ...current, url })); }} />
        </SettingsField> : null}
      </SettingsGroup>
      <SettingsGroup title="服务状态">
        <SettingsField label="模型"><div className={cx("xl:text-right", valueClass)}>SenseVoiceSmall · CPU</div></SettingsField>
        <SettingsField label="连接状态">
          <div className="flex flex-wrap items-center justify-end gap-3">
            {connection.health ? <span role="status" className={valueClass}>{connection.health.ready ? "服务就绪" : "服务未就绪"} · {connection.health.model} · {connection.health.device}</span> : null}
            <button type="button" className={compactGhostButtonClass} disabled={unsettled || connection.busy} onClick={() => void connection.check()}>检查连接</button>
          </div>
        </SettingsField>
        {draft.connection_mode === "managed" ? <SettingsField label="托管环境" layout="stack">
          <ManagedRuntimePanel client={client} host={host} importExtensions={["zip"]} disabled={unsettled} />
        </SettingsField> : null}
      </SettingsGroup>
    </> : null}
    <TranscriptionTest client={client} host={host} />
  </div>;
}
