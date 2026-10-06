import type { RoleRecord } from "@yinfengwindy/shiori-sdk";
import type { RoleVoiceProviderSettings } from "../shared/types";
import { readProviderVoiceSettings, roleVoiceProviderSnapshots, serializeProviderVoiceSettings, voiceSettingsRecord, type RoleVoiceForm } from "./roleVoiceProviderSettings";

/** Normalized role-owned TTS settings used by form and persistence selectors. */
export type RoleVoiceConfig = RoleVoiceProviderSettings & {
  enabled: boolean;
  provider: string;
  providerSettings: Record<string, RoleVoiceProviderSettings>;
};

/** Reads provider-scoped settings and preserves legacy MiniMax role bindings. */
export function readRoleVoiceConfig(role: Pick<RoleRecord, "runtime_config"> | null): RoleVoiceConfig {
  const raw = voiceSettingsRecord(role?.runtime_config?.tts);
  const provider = String(raw.provider ?? "minimax").trim();
  const saved = voiceSettingsRecord(raw.providers);
  // Once scoped settings exist, another provider's active mirror is not a fallback.
  const selected = readProviderVoiceSettings(saved[provider] ?? (Object.keys(saved).length ? {} : raw));
  return {
    enabled: raw.enabled !== false,
    provider,
    ...selected,
    providerSettings: {
      ...Object.fromEntries(Object.entries(saved).map(([id, values]) => [id, readProviderVoiceSettings(values)])),
      [provider]: selected,
    },
  };
}

/** Writes selected and inactive provider settings while preserving plugin-specific fields. */
export function writeRoleVoiceConfigToRuntimeConfig(runtimeConfig: Record<string, unknown>, roleForm: RoleVoiceForm): Record<string, unknown> {
  const previous = voiceSettingsRecord(runtimeConfig.tts);
  const saved = voiceSettingsRecord(previous.providers);
  const snapshots = roleVoiceProviderSnapshots(roleForm);
  const provider = roleForm.voiceProvider.trim();
  return {
    ...runtimeConfig,
    tts: {
      ...previous,
      enabled: Boolean(roleForm.voiceEnabled),
      provider,
      ...serializeProviderVoiceSettings(snapshots[provider]),
      providers: {
        ...saved,
        ...Object.fromEntries(Object.entries(snapshots).map(([id, settings]) => [id, {
          ...voiceSettingsRecord(saved[id]), ...serializeProviderVoiceSettings(settings),
        }])),
      },
    },
  };
}

/** Compares active and inactive voice drafts with persisted role data. */
export function roleVoiceConfigEqual(roleForm: RoleVoiceForm, persisted: RoleVoiceConfig): boolean {
  return Boolean(roleForm.voiceEnabled) === persisted.enabled
    && roleForm.voiceProvider.trim() === persisted.provider
    && settingsKey(roleVoiceProviderSnapshots(roleForm)) === settingsKey(persisted.providerSettings);
}

function settingsKey(settings: Record<string, RoleVoiceProviderSettings>) {
  return JSON.stringify(Object.entries(settings).sort(([left], [right]) => left.localeCompare(right)));
}
