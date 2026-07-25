import type { RoleFormState, RoleRecord } from "../shared/types";

export const minimaxVoiceEmotionOptions = [
  "happy",
  "sad",
  "angry",
  "fearful",
  "disgusted",
  "surprised",
  "calm",
  "whisper",
] as const;

export type RoleVoiceConfig = {
  enabled: boolean;
  provider: string;
  voiceId: string;
  voiceName: string;
  speed: number;
  moodTtsEmotions: Record<string, string>;
};

/** Normalizes one role-owned MiniMax voice configuration. */
export function readRoleVoiceConfig(role: Pick<RoleRecord, "runtime_config"> | null): RoleVoiceConfig {
  const runtimeConfig = role?.runtime_config ?? {};
  const raw = runtimeConfig.tts && typeof runtimeConfig.tts === "object" && !Array.isArray(runtimeConfig.tts)
    ? runtimeConfig.tts as Record<string, unknown>
    : {};
  const speed = Number(raw.speed ?? 1);
  const moodTtsEmotions = normalizeMoodTtsEmotions(raw.mood_tts_emotions);
  return {
    enabled: raw.enabled !== false,
    provider: String(raw.provider ?? "minimax").trim() || "minimax",
    voiceId: String(raw.voice_id ?? "").trim(),
    voiceName: String(raw.voice_name ?? "").trim(),
    speed: Number.isFinite(speed) && speed >= 0.5 && speed <= 2 ? speed : 1,
    moodTtsEmotions,
  };
}

/** Writes role-owned voice fields while preserving unrelated runtime settings. */
export function writeRoleVoiceConfigToRuntimeConfig(
  runtimeConfig: Record<string, unknown>,
  roleForm: Pick<RoleFormState, "voiceEnabled" | "voiceId" | "voiceName" | "voiceSpeed" | "voiceMoodEmotions">,
): Record<string, unknown> {
  const previous = runtimeConfig.tts && typeof runtimeConfig.tts === "object" && !Array.isArray(runtimeConfig.tts)
    ? runtimeConfig.tts as Record<string, unknown>
    : {};
  const speed = Number(roleForm.voiceSpeed);
  return {
    ...runtimeConfig,
    tts: {
      ...previous,
      enabled: Boolean(roleForm.voiceEnabled),
      provider: String(previous.provider ?? "minimax").trim() || "minimax",
      voice_id: String(roleForm.voiceId ?? "").trim(),
      voice_name: String(roleForm.voiceName ?? "").trim(),
      speed: Number.isFinite(speed) && speed >= 0.5 && speed <= 2 ? speed : 1,
      mood_tts_emotions: normalizeMoodTtsEmotions(roleForm.voiceMoodEmotions),
    },
  };
}

/** Compares editable role voice settings with persisted runtime data. */
export function roleVoiceConfigEqual(
  roleForm: Pick<RoleFormState, "voiceEnabled" | "voiceId" | "voiceName" | "voiceSpeed" | "voiceMoodEmotions">,
  persisted: RoleVoiceConfig,
): boolean {
  const speed = Number(roleForm.voiceSpeed);
  return Boolean(roleForm.voiceEnabled) === persisted.enabled
    && String(roleForm.voiceId ?? "").trim() === persisted.voiceId
    && String(roleForm.voiceName ?? "").trim() === persisted.voiceName
    && (Number.isFinite(speed) && speed >= 0.5 && speed <= 2 ? speed : 1) === persisted.speed
    && JSON.stringify(normalizeMoodTtsEmotions(roleForm.voiceMoodEmotions)) === JSON.stringify(persisted.moodTtsEmotions);
}

function normalizeMoodTtsEmotions(raw: unknown): Record<string, string> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const allowed = new Set<string>(minimaxVoiceEmotionOptions);
  return Object.fromEntries(
    Object.entries(raw)
      .map(([mood, value]) => [mood.trim(), String(value ?? "").trim()] as const)
      .filter(([mood, value]) => mood && allowed.has(value)),
  );
}
