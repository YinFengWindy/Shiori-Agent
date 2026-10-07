import type { NativeAudioDevice, PluginServiceDescriptor, PluginServiceReference, SelectOption } from "@yinfengwindy/shiori-sdk";
import type { VoicePreferences } from "../background/voice/preferences";

/** The two speech services the desktop pet's voice needs, as keys of `VoicePreferences`. */
export type VoiceProviderKind = "asr" | "tts";

/** Row labels of the provider fields, also used in their hints. */
export const voiceProviderLabels: Record<VoiceProviderKind, string> = { asr: "语音识别", tts: "语音合成" };

/** Why the voice toggle cannot be turned on, or undefined once both providers are chosen. */
export function voiceToggleBlockedReason(draft: VoicePreferences) {
  return draft.asr && draft.tts ? undefined : "需先选择语音识别与语音合成";
}

/** The `Select` value of one service reference; empty for none. */
export function providerValue(reference: PluginServiceReference | null) {
  return reference ? JSON.stringify({ plugin_id: reference.plugin_id, service_id: reference.service_id }) : "";
}

/** Inputs of one provider row: what is installed (null while listing), what is saved, and the voice state. */
export type ProviderFieldInput = {
  kind: VoiceProviderKind;
  available: PluginServiceDescriptor[] | null;
  listError: string;
  selected: PluginServiceReference | null;
  voiceEnabled: boolean;
};

/**
 * Derives one provider row: its options, whether it can be changed, and the
 * short hint. A saved provider that is no longer installed stays visible as
 * 「（不可用）」; 「未选择」 is withheld while voice is on, since voice needs both.
 */
export function providerFieldView({ kind, available, listError, selected, voiceEnabled }: ProviderFieldInput) {
  const value = providerValue(selected);
  const options: SelectOption[] = (available ?? []).map((provider) => ({ value: providerValue(provider), label: provider.label }));
  if (selected && !options.some((option) => option.value === value)) options.push({ value, label: `${selected.plugin_id}（不可用）` });
  // Keep 「未选择」 representable when voice is on without a provider (an older document).
  const allowNone = !voiceEnabled || !selected;
  const label = voiceProviderLabels[kind];
  const hint = listError
    ? `${label}列表读取失败：${listError}`
    : available?.length === 0
      ? `未安装${label}插件`
      : voiceEnabled && selected ? "开启桌宠语音时必选" : undefined;
  return {
    value,
    options: allowNone ? [{ value: "", label: "未选择" }, ...options] : options,
    disabled: !available?.length,
    hint,
    /** The reference a picked option stands for; null means none and is refused while voice is on. */
    resolve: (next: string): PluginServiceReference | null | undefined => {
      const provider = available?.find((item) => providerValue(item) === next);
      if (provider) return { plugin_id: provider.plugin_id, service_id: provider.service_id };
      return next === "" && allowNone ? null : undefined;
    },
  };
}

/** Microphone options: the system default, the listed devices, and a saved device that is not listed. */
export function microphoneOptions(devices: NativeAudioDevice[], savedDeviceId: string): SelectOption[] {
  const options = [{ value: "", label: "系统默认" }, ...devices.map((device) => ({ value: device.deviceId, label: device.label || device.deviceId }))];
  if (savedDeviceId && !options.some((option) => option.value === savedDeviceId)) options.push({ value: savedDeviceId, label: savedDeviceId });
  return options;
}
