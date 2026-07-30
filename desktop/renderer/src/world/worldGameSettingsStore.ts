export type WorldGameSettings = {
  textSpeed: "slow" | "normal" | "fast";
  autoPlay: boolean;
  voiceVolume: number;
  musicVolume: number;
  ambienceVolume: number;
  effectsVolume: number;
  reducedMotion: boolean;
};

const storageKey = "shiori.world-game-settings.v1";

export const defaultWorldGameSettings: WorldGameSettings = {
  textSpeed: "normal",
  autoPlay: false,
  voiceVolume: 100,
  musicVolume: 70,
  ambienceVolume: 70,
  effectsVolume: 80,
  reducedMotion: false,
};

/** Reads versioned World-only presentation preferences without affecting desktop settings. */
export function readWorldGameSettings(): WorldGameSettings {
  try {
    const raw = globalThis.localStorage?.getItem(storageKey);
    if (!raw) return defaultWorldGameSettings;
    const value = JSON.parse(raw) as Partial<WorldGameSettings>;
    return {
      ...defaultWorldGameSettings,
      ...value,
      textSpeed: value.textSpeed === "slow" || value.textSpeed === "fast" ? value.textSpeed : "normal",
      voiceVolume: clampVolume(value.voiceVolume, defaultWorldGameSettings.voiceVolume),
      musicVolume: clampVolume(value.musicVolume, defaultWorldGameSettings.musicVolume),
      ambienceVolume: clampVolume(value.ambienceVolume, defaultWorldGameSettings.ambienceVolume),
      effectsVolume: clampVolume(value.effectsVolume, defaultWorldGameSettings.effectsVolume),
    };
  } catch {
    return defaultWorldGameSettings;
  }
}

/** Persists World-only presentation preferences under a versioned renderer key. */
export function writeWorldGameSettings(settings: WorldGameSettings): void {
  globalThis.localStorage?.setItem(storageKey, JSON.stringify(settings));
}

function clampVolume(value: number | undefined, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : fallback;
}
