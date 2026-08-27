import { SettingsField as Field } from "./SettingsField";
import {
  SettingsSecretInput,
  SettingsSectionCard,
  settingsInputClass,
} from "./SettingsFieldPrimitives";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";
import { VoiceInputSettingsSection } from "./VoiceInputSettingsSection";

/** Renders global voice provider and input preferences. */
export function VoiceSettingsSection({ draft, subsectionId, updateDraft }: SettingsSectionEditorProps) {
  if (subsectionId === "input") {
    return <VoiceInputSettingsSection draft={draft} updateDraft={updateDraft} />;
  }
  return (
    <SettingsSectionCard>
      <Field label="ASR Provider">
        <select className={settingsInputClass} value={draft.voice.asrProvider} onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, asrProvider: event.target.value } }))}>
          <option value="tencent">tencent</option>
        </select>
      </Field>
      <Field label="腾讯云 ASR 地址">
        <input className={settingsInputClass} value={draft.voice.asrBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, asrBaseUrl: event.target.value } }))} />
      </Field>
      <Field label="腾讯云 SecretId">
        <SettingsSecretInput value={draft.voice.asrSecretId} onChange={(value) => updateDraft((current) => ({ ...current, voice: { ...current.voice, asrSecretId: value } }))} />
      </Field>
      <Field label="腾讯云 SecretKey">
        <SettingsSecretInput value={draft.voice.asrSecretKey} onChange={(value) => updateDraft((current) => ({ ...current, voice: { ...current.voice, asrSecretKey: value } }))} />
      </Field>
      <Field label="TTS Provider">
        <select className={settingsInputClass} value={draft.voice.ttsProvider} onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, ttsProvider: event.target.value } }))}>
          <option value="minimax">minimax</option>
        </select>
      </Field>
      <Field label="MiniMax TTS 地址">
        <input className={settingsInputClass} value={draft.voice.ttsBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, ttsBaseUrl: event.target.value } }))} />
      </Field>
      <Field label="TTS 模型">
        <input className={settingsInputClass} value={draft.voice.ttsModel} onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, ttsModel: event.target.value } }))} />
      </Field>
      <Field label="MiniMax API Key">
        <SettingsSecretInput value={draft.voice.ttsApiKey} onChange={(value) => updateDraft((current) => ({ ...current, voice: { ...current.voice, ttsApiKey: value } }))} />
      </Field>
      <Field label={`TTS 音量 (${draft.voice.ttsVolume.toFixed(1)})`}>
        <input
          aria-label="TTS 音量"
          className="w-full accent-primary"
          type="range"
          min="0.1"
          max="10"
          step="0.1"
          value={draft.voice.ttsVolume}
          onChange={(event) => updateDraft((current) => ({
            ...current,
            voice: { ...current.voice, ttsVolume: Number(event.target.value) },
          }))}
        />
      </Field>
    </SettingsSectionCard>
  );
}
