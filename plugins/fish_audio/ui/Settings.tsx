import { useState } from "react";
import { compactGhostButtonClass, Select, SettingsField, SettingsGroup, settingsGroupStackClass, settingsInputClass, usePrivateAutosave, type PluginSettingsSectionComponentProps } from "@yinfengwindy/shiori-sdk";
import { rpcMethods } from "../rpcMethods.generated";
import type { FishSettings } from "../shared/contracts";
import { TranscriptionTest } from "./TranscriptionTest";

type SettingsDraft = FishSettings & { api_key: string; clear_api_key: boolean };
const models = [{ value: "s2.1-pro-free", label: "S2.1 Pro Free（免费 TTS）" }, { value: "s2.1-pro", label: "S2.1 Pro（付费）" }, { value: "s2-pro", label: "S2 Pro（付费）" }];

/** Global cloud credentials and models only; voices are edited on each role's card. */
export function FishSettingsPage({ client, host }: PluginSettingsSectionComponentProps) {
  const [key, setKey] = useState("");
  const state = usePrivateAutosave<SettingsDraft>(client, "settings", {
    load: async () => ({ ...await client.call<FishSettings>(rpcMethods["settings.get"]), api_key: "", clear_api_key: false }),
    save: async (value) => ({ ...await client.call<FishSettings>(rpcMethods["settings.set"], { tts_model: value.tts_model, api_key: value.api_key, clear_api_key: value.clear_api_key }), api_key: "", clear_api_key: false }),
  });
  const draft = state.draft;
  return <div className={settingsGroupStackClass}>
    <host.ui.SettingsSavedStatus phase={state.savePhase} />
    {state.loadError ? <host.ui.InlineError message={state.loadError} actions={<button type="button" className={compactGhostButtonClass} onClick={state.reload}>重新加载</button>} /> : null}
    {state.saveError ? <host.ui.InlineError message={state.saveError} actions={<button type="button" className={compactGhostButtonClass} onClick={state.retry}>重试</button>} /> : null}
    {draft ? <SettingsGroup title="Fish Audio">
      <SettingsField label="API Key">
        <div className="grid gap-2">
          <input aria-label="Fish Audio API Key" type="password" autoComplete="new-password" className={settingsInputClass} value={key} maxLength={4096} placeholder={draft.has_api_key ? "已配置，输入新 Key 替换" : "未配置"} onChange={(event) => setKey(event.target.value)} />
          <div className="flex justify-end gap-2">
            <button type="button" className={compactGhostButtonClass} disabled={!key.trim() || state.savePhase === "saving"} onClick={() => { state.commit((current) => ({ ...current, api_key: key, clear_api_key: false })); setKey(""); }}>保存 Key</button>
            <button type="button" className={compactGhostButtonClass} disabled={!draft.has_api_key || state.savePhase === "saving"} onClick={() => state.commit((current) => ({ ...current, api_key: "", clear_api_key: true }))}>清除 Key</button>
          </div>
        </div>
      </SettingsField>
      <SettingsField label="语音合成模型">
        <Select aria-label="Fish Audio TTS 模型" className={settingsInputClass} value={draft.tts_model} options={models} onValueChange={(model) => {
          if (model === "s2.1-pro-free" || model === "s2.1-pro" || model === "s2-pro") state.commit((current) => ({ ...current, tts_model: model }));
        }} />
      </SettingsField>
      <SettingsField label="语音识别模型"><span className="text-body-sm text-ink-secondary">transcribe-1-pro（付费）</span></SettingsField>
    </SettingsGroup> : null}
    <TranscriptionTest client={client} host={host} />
  </div>;
}
