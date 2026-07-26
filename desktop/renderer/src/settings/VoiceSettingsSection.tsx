import { SettingsField as Field } from "./SettingsField";
import {
  SettingsSecretInput,
  SettingsSectionCard,
} from "./SettingsFieldPrimitives";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";
import { cx, inputClass } from "../shared/styles";
import { VoiceInputSettingsSection } from "./VoiceInputSettingsSection";

/** Renders global voice provider and input preferences. */
export function VoiceSettingsSection({ draft, subsectionId, updateDraft }: SettingsSectionEditorProps) {
  if (subsectionId === "input") {
    return <VoiceInputSettingsSection draft={draft} updateDraft={updateDraft} />;
  }
  return (
    <SettingsSectionCard>
      <Field label="ASR Provider">
        <input className={cx(inputClass, "bg-white")} value={draft.voice.asrProvider} onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, asrProvider: event.target.value } }))} />
      </Field>
      <Field label="腾讯云 ASR 地址">
        <input className={cx(inputClass, "bg-white")} value={draft.voice.asrBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, asrBaseUrl: event.target.value } }))} />
      </Field>
      <Field label="腾讯云 SecretId">
        <SettingsSecretInput value={draft.voice.asrSecretId} onChange={(value) => updateDraft((current) => ({ ...current, voice: { ...current.voice, asrSecretId: value } }))} />
      </Field>
      <Field label="腾讯云 SecretKey">
        <SettingsSecretInput value={draft.voice.asrSecretKey} onChange={(value) => updateDraft((current) => ({ ...current, voice: { ...current.voice, asrSecretKey: value } }))} />
      </Field>
      <Field label="TTS Provider">
        <input className={cx(inputClass, "bg-white")} value={draft.voice.ttsProvider} onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, ttsProvider: event.target.value } }))} />
      </Field>
      <Field label="MiniMax TTS 地址">
        <input className={cx(inputClass, "bg-white")} value={draft.voice.ttsBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, ttsBaseUrl: event.target.value } }))} />
      </Field>
      <Field label="TTS 模型">
        <input className={cx(inputClass, "bg-white")} value={draft.voice.ttsModel} onChange={(event) => updateDraft((current) => ({ ...current, voice: { ...current.voice, ttsModel: event.target.value } }))} />
      </Field>
      <Field label="MiniMax API Key">
        <SettingsSecretInput value={draft.voice.ttsApiKey} onChange={(value) => updateDraft((current) => ({ ...current, voice: { ...current.voice, ttsApiKey: value } }))} />
      </Field>
    </SettingsSectionCard>
  );
}
