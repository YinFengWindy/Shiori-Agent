export type StoryPreferences = {
  textSpeed: "slow" | "normal" | "fast";
  showFullText: boolean;
  autoPlay: boolean;
  autoPlayDelayMs: number;
  skipReadTextOnly: boolean;
  motionIntensity: "reduced" | "standard" | "cinematic";
  voiceVolume: number;
  musicVolume: number;
  ambienceVolume: number;
  effectsVolume: number;
  reducedMotion: boolean;
};

const storageKey = "shiori.story-preferences.v1";

export const defaultStoryPreferences: StoryPreferences = {
  textSpeed: "normal",
  showFullText: false,
  autoPlay: false,
  autoPlayDelayMs: 1200,
  skipReadTextOnly: true,
  motionIntensity: "standard",
  voiceVolume: 100,
  musicVolume: 70,
  ambienceVolume: 70,
  effectsVolume: 80,
  reducedMotion: false,
};

/** Reads Story presentation preferences without affecting desktop settings. */
export function readStoryPreferences(): StoryPreferences {
  try {
    const raw = globalThis.localStorage?.getItem(storageKey);
    if (!raw) return defaultStoryPreferences;
    const value = JSON.parse(raw) as Partial<StoryPreferences>;
    return {
      ...defaultStoryPreferences,
      ...value,
      textSpeed: value.textSpeed === "slow" || value.textSpeed === "fast" ? value.textSpeed : "normal",
      autoPlayDelayMs: clampDelay(value.autoPlayDelayMs),
      motionIntensity: value.motionIntensity === "reduced" || value.motionIntensity === "cinematic" ? value.motionIntensity : "standard",
      voiceVolume: clampVolume(value.voiceVolume, defaultStoryPreferences.voiceVolume),
      musicVolume: clampVolume(value.musicVolume, defaultStoryPreferences.musicVolume),
      ambienceVolume: clampVolume(value.ambienceVolume, defaultStoryPreferences.ambienceVolume),
      effectsVolume: clampVolume(value.effectsVolume, defaultStoryPreferences.effectsVolume),
    };
  } catch {
    return defaultStoryPreferences;
  }
}

/** Persists Story presentation preferences under a versioned renderer key. */
export function writeStoryPreferences(settings: StoryPreferences): void {
  globalThis.localStorage?.setItem(storageKey, JSON.stringify(settings));
}

function clampVolume(value: number | undefined, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : fallback;
}

function clampDelay(value: number | undefined): number {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.min(5_000, Math.max(300, Math.round(value)))
    : defaultStoryPreferences.autoPlayDelayMs;
}
