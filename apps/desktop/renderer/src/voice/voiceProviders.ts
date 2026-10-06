import type { SelectOption } from "@yinfengwindy/shiori-sdk";
import type { VoiceProviderDescriptor } from "../../../src/bridge/shared";

/** Keeps a missing selection visible without selecting a different provider. */
export function voiceProviderOptions(providers: readonly VoiceProviderDescriptor[], kind: VoiceProviderDescriptor["kind"], selected: string, loading = false): SelectOption[] {
  const options = providers.filter((provider) => provider.kind === kind).map((provider) => ({
    value: provider.id,
    label: provider.available ? provider.label : `${provider.label}（不可用）`,
    disabled: !provider.available,
  }));
  if (selected && !options.some((option) => option.value === selected)) {
    options.push({ value: selected, label: loading ? selected : `${selected}（不可用）`, disabled: true });
  }
  return selected ? options : [{ value: "", label: "未选择", disabled: true }, ...options];
}

/** Preserves an unsupported saved emotion so discovery never silently rewrites it. */
export function voiceEmotionOptions(emotions: readonly string[], selected: string): SelectOption[] {
  const options: SelectOption[] = [{ value: "", label: "自动判断" }, ...emotions.map((value) => ({ value, label: value }))];
  if (selected && !emotions.includes(selected)) options.push({ value: selected, label: `${selected}（不受支持）`, disabled: true });
  return options;
}
