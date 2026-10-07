import { compactGhostButtonClass, Select, SettingsField, SettingsGroup, settingsGroupStackClass, settingsInputClass, usePrivateAutosave, type PluginSettingsSectionComponentProps, type SelectOption } from "@yinfengwindy/shiori-sdk";
import type { GptSoVitsSettings } from "../shared/contracts";
import { ServiceStatusGroup } from "./ServiceStatusGroup";
import { useServiceHealth } from "./useServiceHealth";

const connectionModeOptions: SelectOption[] = [{ value: "external", label: "外部服务" }, { value: "managed", label: "插件托管" }];
const externalFields = [["url", "服务地址"], ["gpt_weights", "GPT 权重路径"], ["sovits_weights", "SoVITS 权重路径"]] as const;

/** Autosaves provider-owned service paths and distinguishes reachability from model verification. */
export function GptSoVitsSettingsPage({ client, host }: PluginSettingsSectionComponentProps) {
  const health = useServiceHealth(client);
  const state = usePrivateAutosave<GptSoVitsSettings>(client, "settings", {
    load: () => client.call<GptSoVitsSettings>("settings.get"),
    // A stored change makes an earlier health result describe the previous service.
    save: async (value) => { const result = await client.call<GptSoVitsSettings>("settings.set", value); health.clear(); return result; },
  });
  const draft = state.draft;
  return <div className={settingsGroupStackClass}>
    <host.ui.SettingsSavedStatus phase={state.savePhase} />
    {state.loadError ? <host.ui.InlineError message={state.loadError} actions={<button type="button" className={compactGhostButtonClass} onClick={state.reload}>重新加载</button>} /> : null}
    {state.saveError ? <host.ui.InlineError message={state.saveError} actions={<button type="button" className={compactGhostButtonClass} onClick={state.retry}>重试</button>} /> : null}
    {health.error ? <host.ui.InlineError message={health.error} /> : null}
    {!draft && state.loading ? <span className="text-body-sm text-ink-muted">正在读取设置…</span> : null}
    {draft ? <>
      <SettingsGroup title="连接">
        <SettingsField label="连接模式">
          <Select aria-label="连接模式" className={settingsInputClass} value={draft.connection_mode} options={connectionModeOptions} onValueChange={(mode) => state.update((current) => ({ ...current, connection_mode: mode === "managed" ? "managed" : "external" }))} />
        </SettingsField>
        {draft.connection_mode === "external" ? externalFields.map(([field, label]) => <SettingsField key={field} label={label}>
          <input aria-label={label} className={settingsInputClass} value={draft[field]} onChange={(event) => { const value = event.target.value; state.update((current) => ({ ...current, [field]: value })); }} />
        </SettingsField>) : null}
      </SettingsGroup>
      {/* Service actions act on the stored settings, so they wait while an edit is unsaved or its save failed. */}
      <ServiceStatusGroup client={client} host={host} mode={draft.connection_mode} version={draft.version} health={health} disabled={state.savePhase !== "idle"} />
    </> : null}
  </div>;
}
