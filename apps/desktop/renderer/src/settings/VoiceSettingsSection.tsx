import { Select } from "@yinfengwindy/shiori-sdk";
import { SettingsField as Field } from "./SettingsField";
import { SettingsGroup, SettingsToggleField, settingsGroupStackClass, settingsInputClass } from "./SettingsFieldPrimitives";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";
import { VoiceInputSettingsSection } from "./VoiceInputSettingsSection";
import { useVoiceProviders } from "../voice/useVoiceProviders";
import { voiceProviderOptions } from "../voice/voiceProviders";
import { InlineError } from "../shared/feedback/InlineError";

/** Renders global speech selection; plugin configuration owns provider credentials. */
export function VoiceSettingsSection(props: SettingsSectionEditorProps) {
  return props.subsectionId === "input"
    ? <VoiceInputSettingsSection draft={props.draft} updateDraft={props.updateDraft} />
    : <VoiceProviderSettings draft={props.draft} updateDraft={props.updateDraft} />;
}

function VoiceProviderSettings({ draft, updateDraft }: Pick<SettingsSectionEditorProps, "draft" | "updateDraft">) {
  const { providers, loading, error } = useVoiceProviders();
  const setVoice = (patch: Partial<SettingsSectionEditorProps["draft"]["voice"]>) => updateDraft((current) => ({
    ...current, voice: { ...current.voice, ...patch },
  }));
  return (
    <div className={settingsGroupStackClass}>
      {error ? <InlineError persona={false} message={error} /> : null}
      <SettingsGroup title="语音识别">
        <SettingsToggleField label="语音识别" checked={draft.voice.asrEnabled ?? draft.voice.enabled} onChange={(asrEnabled) => setVoice({ asrEnabled })} />
        <Field label="服务商">
          <Select aria-label="语音识别服务商" className={settingsInputClass} value={draft.voice.asrProvider} disabled={loading} onValueChange={(asrProvider) => setVoice({ asrProvider })} options={voiceProviderOptions(providers, "asr", draft.voice.asrProvider, loading)} />
        </Field>
      </SettingsGroup>
      <SettingsGroup title="语音合成">
        <SettingsToggleField label="语音合成" checked={draft.voice.ttsEnabled ?? draft.voice.enabled} onChange={(ttsEnabled) => setVoice({ ttsEnabled })} />
        <Field label="服务商">
          <Select aria-label="语音合成服务商" className={settingsInputClass} value={draft.voice.ttsProvider} disabled={loading} onValueChange={(ttsProvider) => setVoice({ ttsProvider })} options={voiceProviderOptions(providers, "tts", draft.voice.ttsProvider, loading)} />
        </Field>
      </SettingsGroup>
    </div>
  );
}
