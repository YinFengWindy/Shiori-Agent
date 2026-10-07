import { Select, SettingsField, SettingsGroup, settingsInputClass, SettingsToggleField, type NativeAudioDevice, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { VoicePreferences } from "../background/voice/preferences";
import type { VoiceProviderLists } from "./useVoiceEnvironment";
import { VoiceHotkeyField } from "./VoiceHotkeyField";
import { microphoneOptions, providerFieldView, voiceProviderLabels, voiceToggleBlockedReason, type VoiceProviderKind } from "./voiceSettingsModel";

/** An edit of the preferences draft (`usePrivateAutosave`'s `update` / `commit`). */
type DraftChange = (change: (current: VoicePreferences) => VoicePreferences) => void;

/** Props of `VoiceGroup`, the 「语音」 card. */
export type VoiceGroupProps = {
  client: PluginRpcClient;
  draft: VoicePreferences;
  devices: NativeAudioDevice[];
  devicesError: string;
  update: DraftChange;
  commit: DraftChange;
};

/** The 「语音」 card: the voice switch, its hotkey and the microphone. */
export function VoiceGroup({ client, draft, devices, devicesError, update, commit }: VoiceGroupProps) {
  const blocked = voiceToggleBlockedReason(draft);
  return (
    <SettingsGroup title="语音">
      <SettingsToggleField
        label="桌宠语音"
        hint={blocked}
        checked={draft.enabled}
        // Turning off is always allowed; turning on needs both providers.
        disabled={!draft.enabled && Boolean(blocked)}
        onChange={(enabled) => {
          if (enabled && blocked) return;
          update((current) => ({ ...current, enabled }));
        }}
      />
      <VoiceHotkeyField client={client} value={draft.hotkey} onCommit={(hotkey) => commit((current) => ({ ...current, hotkey }))} />
      <SettingsField label="麦克风" hint={devicesError ? `麦克风列表读取失败：${devicesError}` : undefined}>
        <Select
          aria-label="麦克风"
          className={settingsInputClass}
          value={draft.microphone_device_id}
          options={microphoneOptions(devices, draft.microphone_device_id)}
          onValueChange={(microphone_device_id) => update((current) => ({ ...current, microphone_device_id }))}
        />
      </SettingsField>
    </SettingsGroup>
  );
}

/** Props of `VoiceServicesGroup`, the 「语音服务」 card. */
export type VoiceServicesGroupProps = {
  draft: VoicePreferences;
  /** Installed providers; null while they are being listed. */
  providers: VoiceProviderLists | null;
  providersError: string;
  update: DraftChange;
};

/** The 「语音服务」 card: which installed plugins recognise and synthesise speech. */
export function VoiceServicesGroup({ draft, providers, providersError, update }: VoiceServicesGroupProps) {
  return (
    <SettingsGroup title="语音服务">
      {(["asr", "tts"] as const).map((kind: VoiceProviderKind) => {
        const view = providerFieldView({
          kind, available: providers?.[kind] ?? null, listError: providersError, selected: draft[kind], voiceEnabled: draft.enabled,
        });
        const label = voiceProviderLabels[kind];
        return (
          <SettingsField key={kind} label={label} hint={view.hint}>
            <Select
              aria-label={label}
              className={settingsInputClass}
              disabled={view.disabled}
              value={view.value}
              options={view.options}
              onValueChange={(next) => {
                const reference = view.resolve(next);
                if (reference !== undefined) update((current) => ({ ...current, [kind]: reference }));
              }}
            />
          </SettingsField>
        );
      })}
    </SettingsGroup>
  );
}
