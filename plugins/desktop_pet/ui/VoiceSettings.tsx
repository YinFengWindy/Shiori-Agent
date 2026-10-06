import { useEffect, useRef, useState } from "react";
import { errorMessage, ghostButtonClass, inputClass, Select, SettingsToggleCard, type NativeAudioDevice, type PluginServiceDescriptor, type PluginSettingsSectionComponentProps } from "@yinfengwindy/shiori-sdk";
import type { VoicePreferences } from "../background/voice/preferences";

/** Desktop pet preferences live in its private backend storage, independently of host settings. */
export function VoiceSettings({ client, host }: PluginSettingsSectionComponentProps) {
  const [saved, setSaved] = useState<VoicePreferences | null>(null);
  const [draft, setDraft] = useState<VoicePreferences | null>(null);
  const [providers, setProviders] = useState<PluginServiceDescriptor[]>([]);
  const [devices, setDevices] = useState<NativeAudioDevice[]>([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const revision = useRef(0);
  useEffect(() => {
    let active = true;
    revision.current += 1;
    void Promise.all([
      client.call<VoicePreferences>("voice.preferences.get"),
      client.services.list("shiori.asr.v1"), client.services.list("shiori.tts.v1"),
    ]).then(([preferences, asr, tts]) => {
      if (active) { setSaved(preferences); setDraft(preferences); setProviders([...asr.services, ...tts.services]); }
    }).catch((cause) => { if (active) setError(errorMessage(cause)); });
    void client.background.call<NativeAudioDevice[]>("voice.devices").then((result) => { if (active) setDevices(result); }).catch((cause) => { if (active) setError(errorMessage(cause)); });
    return () => { active = false; revision.current += 1; };
  }, [client]);
  const save = async () => {
    if (!draft) return;
    const currentRevision = revision.current;
    setSaving(true); setError("");
    try {
      await client.background.call("voice.preferences.validate", { hotkey: draft.hotkey });
      const result = await client.call<VoicePreferences>("voice.preferences.set", draft);
      if (revision.current === currentRevision) { setSaved(result); setDraft(result); }
    }
    catch (cause) { if (revision.current === currentRevision) setError(errorMessage(cause)); }
    finally { if (revision.current === currentRevision) setSaving(false); }
  };
  return <div className="grid gap-4">
    {error ? <host.ui.InlineError message={error} /> : null}
    {draft ? <>
      <div className="flex items-center justify-between"><span>桌宠语音</span><SettingsToggleCard disabled={saving} checked={draft.enabled} ariaLabel="桌宠语音" onChange={(enabled) => setDraft({ ...draft, enabled })} /></div>
      <label className="grid gap-2">快捷键<input className={inputClass} disabled={saving} value={draft.hotkey} onChange={(event) => setDraft({ ...draft, hotkey: event.target.value })} /></label>
      <label className="grid gap-2">麦克风<Select disabled={saving} aria-label="麦克风" className={inputClass} value={draft.microphone_device_id} onValueChange={(microphone_device_id) => setDraft({ ...draft, microphone_device_id })} options={[{ value: "", label: "系统默认" }, ...devices.map((device) => ({ value: device.deviceId, label: device.label || device.deviceId }))]} /></label>
      {(["asr", "tts"] as const).map((kind) => {
        const selected = draft[kind]; const value = selected ? JSON.stringify(selected) : "";
        const options = providers.filter((provider) => provider.contract === `shiori.${kind}.v1`).map((provider) => ({ value: JSON.stringify({ plugin_id: provider.plugin_id, service_id: provider.service_id }), label: provider.label }));
        if (value && !options.some((option) => option.value === value)) options.push({ value, label: `${selected!.plugin_id}（不可用）` });
        return <label key={kind} className="grid gap-2">{kind === "asr" ? "语音识别" : "语音合成"}<Select disabled={saving} aria-label={kind === "asr" ? "语音识别" : "语音合成"} className={inputClass} value={value} options={[{ value: "", label: "未选择" }, ...options]} onValueChange={(next) => {
          const provider = providers.find((item) => JSON.stringify({ plugin_id: item.plugin_id, service_id: item.service_id }) === next);
          setDraft({ ...draft, [kind]: provider ? { plugin_id: provider.plugin_id, service_id: provider.service_id } : null });
        }} /></label>;
      })}
      <div className="flex justify-end"><button type="button" className={ghostButtonClass} disabled={saving || JSON.stringify(saved) === JSON.stringify(draft)} onClick={() => void save()}>{saving ? "保存中…" : "保存"}</button></div>
    </> : <span className="text-ink-muted">正在读取设置…</span>}
  </div>;
}
