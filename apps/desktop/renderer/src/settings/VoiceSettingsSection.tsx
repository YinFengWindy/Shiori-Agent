import { Select } from "../shared/ui/Select";
import { SettingsField as Field } from "./SettingsField";
import {
  SettingsGroup,
  SettingsSecretInput,
  settingsGroupStackClass,
  settingsInputClass,
} from "./SettingsFieldPrimitives";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";
import { VoiceInputSettingsSection } from "./VoiceInputSettingsSection";
import { asrProviderOptions, ttsProviderOptions } from "./voiceProviders";

/** Renders global voice provider and input preferences. */
export function VoiceSettingsSection({ draft, subsectionId, updateDraft }: SettingsSectionEditorProps) {
  if (subsectionId === "input") {
    return <VoiceInputSettingsSection draft={draft} updateDraft={updateDraft} />;
  }
  const setVoice = (patch: Partial<SettingsSectionEditorProps["draft"]["voice"]>) => updateDraft((current) => ({
    ...current,
    voice: { ...current.voice, ...patch },
  }));
  return (
    <div className={settingsGroupStackClass}>
      <SettingsGroup title="语音识别">
        <Field label="服务商">
          <Select aria-label="语音识别服务商" className={settingsInputClass} value={draft.voice.asrProvider} onValueChange={(value) => setVoice({ asrProvider: value })} options={asrProviderOptions} />
        </Field>
        <Field label="服务地址">
          <input aria-label="语音识别服务地址" className={settingsInputClass} value={draft.voice.asrBaseUrl} onChange={(event) => setVoice({ asrBaseUrl: event.target.value })} />
        </Field>
        <Field label="SecretId">
          <SettingsSecretInput ariaLabel="SecretId" value={draft.voice.asrSecretId} onChange={(value) => setVoice({ asrSecretId: value })} />
        </Field>
        <Field label="SecretKey">
          <SettingsSecretInput ariaLabel="SecretKey" value={draft.voice.asrSecretKey} onChange={(value) => setVoice({ asrSecretKey: value })} />
        </Field>
      </SettingsGroup>
      <SettingsGroup title="语音合成">
        <Field label="服务商">
          <Select aria-label="语音合成服务商" className={settingsInputClass} value={draft.voice.ttsProvider} onValueChange={(value) => setVoice({ ttsProvider: value })} options={ttsProviderOptions} />
        </Field>
        <Field label="服务地址">
          <input aria-label="语音合成服务地址" className={settingsInputClass} value={draft.voice.ttsBaseUrl} onChange={(event) => setVoice({ ttsBaseUrl: event.target.value })} />
        </Field>
        <Field label="模型">
          <input aria-label="语音合成模型" className={settingsInputClass} value={draft.voice.ttsModel} onChange={(event) => setVoice({ ttsModel: event.target.value })} />
        </Field>
        <Field label="API Key">
          <SettingsSecretInput ariaLabel="API Key" value={draft.voice.ttsApiKey} onChange={(value) => setVoice({ ttsApiKey: value })} />
        </Field>
        <Field label="音量">
          <div className="flex items-center gap-3">
            <input
              aria-label="TTS 音量"
              className="min-w-0 flex-1 accent-accent"
              type="range"
              min="0.1"
              max="10"
              step="0.1"
              value={draft.voice.ttsVolume}
              onChange={(event) => setVoice({ ttsVolume: Number(event.target.value) })}
            />
            <span className="w-8 shrink-0 text-right text-body-sm tabular-nums text-ink-secondary">{draft.voice.ttsVolume.toFixed(1)}</span>
          </div>
        </Field>
      </SettingsGroup>
    </div>
  );
}
