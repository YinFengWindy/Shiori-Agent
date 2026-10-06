import type { RoleFormState, RoleVoiceProviderSettings } from "../shared/types";

/** The role editor fields that belong to speech configuration. */
export type RoleVoiceForm = Pick<RoleFormState, "voiceEnabled" | "voiceProvider" | "voiceOwnership" | "voiceId" | "voiceName" | "voiceSpeed" | "voiceMoodEmotions" | "voiceProviderSettings">;

/** Reads a persisted mapping without treating malformed optional values as objects. */
export function voiceSettingsRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

/** Provider-specific emotions are opaque strings, validated by the owning provider. */
export function normalizeMoodTtsEmotions(value: unknown) {
  return Object.fromEntries(Object.entries(voiceSettingsRecord(value))
    .map(([mood, emotion]) => [mood.trim(), String(emotion ?? "").trim()] as const)
    .filter(([mood, emotion]) => mood && emotion)
    .sort(([left], [right]) => left.localeCompare(right)));
}

/** Normalizes the shared role voice fields without a provider-specific enum. */
export function readProviderVoiceSettings(value: unknown): RoleVoiceProviderSettings {
  const raw = voiceSettingsRecord(value);
  const speed = Number(raw.speed ?? 1);
  return {
    ownership: raw.ownership === "shiori_managed" ? "shiori_managed" : "external",
    voiceId: String(raw.voice_id ?? "").trim(),
    voiceName: String(raw.voice_name ?? "").trim(),
    speed: Number.isFinite(speed) && speed >= 0.5 && speed <= 2 ? speed : 1,
    moodTtsEmotions: normalizeMoodTtsEmotions(raw.mood_tts_emotions),
  };
}

/** Produces the persisted field names shared with the backend role resolver. */
export function serializeProviderVoiceSettings(settings: RoleVoiceProviderSettings) {
  return { ownership: settings.ownership, voice_id: settings.voiceId, voice_name: settings.voiceName, speed: settings.speed, mood_tts_emotions: settings.moodTtsEmotions };
}

/** Captures the selected provider before navigation or persistence. */
export function roleVoiceProviderSnapshots(form: RoleVoiceForm) {
  return {
    ...form.voiceProviderSettings,
    [form.voiceProvider.trim()]: readProviderVoiceSettings({
      ownership: form.voiceOwnership, voice_id: form.voiceId, voice_name: form.voiceName,
      speed: form.voiceSpeed, mood_tts_emotions: form.voiceMoodEmotions,
    }),
  };
}

/** Switches voices atomically; an unconfigured provider receives no other provider's voice ID. */
export function selectRoleVoiceProvider(form: RoleFormState, provider: string): RoleFormState {
  if (provider === form.voiceProvider) return form;
  const providerSettings = roleVoiceProviderSnapshots(form);
  const next = providerSettings[provider] ?? readProviderVoiceSettings({});
  return {
    ...form, voiceProvider: provider, voiceProviderSettings: providerSettings,
    voiceOwnership: next.ownership, voiceId: next.voiceId, voiceName: next.voiceName,
    voiceSpeed: next.speed, voiceMoodEmotions: next.moodTtsEmotions,
  };
}
