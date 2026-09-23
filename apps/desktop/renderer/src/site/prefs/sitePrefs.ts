/**
 * Visitor preferences for the static site (settings modal + sound toggle),
 * persisted as one versioned JSON value in localStorage.
 *
 * Reading never throws: a missing, corrupt, wrong-version or out-of-range
 * value falls back field by field to the defaults, because a visitor's
 * browser storage is outside our control.
 */

export type TextSpeed = "slow" | "normal" | "fast";

export interface SitePrefs {
  /** 0–100; BGM level (perceptual curve, see sound/soundModel.ts). */
  readonly bgmVolume: number;
  /** 0–100; sound-effect level (perceptual curve, see sound/soundModel.ts). */
  readonly sfxVolume: number;
  readonly textSpeed: TextSpeed;
  /** Master sound switch; off by default (the site starts muted). */
  readonly soundEnabled: boolean;
}

/** The subset of `Storage` the prefs module needs (injectable for tests). */
export type PrefsStorage = Pick<Storage, "getItem" | "setItem">;

export const SITE_PREFS_STORAGE_KEY = "shiori-site-prefs";
const SITE_PREFS_VERSION = 1;

export const DEFAULT_SITE_PREFS: SitePrefs = {
  bgmVolume: 60,
  sfxVolume: 70,
  textSpeed: "normal",
  soundEnabled: false,
};

export const TEXT_SPEEDS: readonly TextSpeed[] = ["slow", "normal", "fast"];

/** Typewriter delay per character for each text speed. */
export const TEXT_SPEED_MS_PER_CHAR: Record<TextSpeed, number> = {
  slow: 75,
  normal: 45,
  fast: 20,
};

function parseVolume(value: unknown, fallback: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return fallback;
  return Math.round(Math.min(100, Math.max(0, value)));
}

/** Normalize any stored value into valid prefs, keeping each valid field. */
export function parseSitePrefs(raw: string | null): SitePrefs {
  if (raw === null) return DEFAULT_SITE_PREFS;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return DEFAULT_SITE_PREFS;
  }
  if (typeof data !== "object" || data === null) return DEFAULT_SITE_PREFS;
  const record = data as Record<string, unknown>;
  if (record.version !== SITE_PREFS_VERSION) return DEFAULT_SITE_PREFS;
  return {
    bgmVolume: parseVolume(record.bgmVolume, DEFAULT_SITE_PREFS.bgmVolume),
    sfxVolume: parseVolume(record.sfxVolume, DEFAULT_SITE_PREFS.sfxVolume),
    textSpeed: TEXT_SPEEDS.includes(record.textSpeed as TextSpeed) ? (record.textSpeed as TextSpeed) : DEFAULT_SITE_PREFS.textSpeed,
    soundEnabled: typeof record.soundEnabled === "boolean" ? record.soundEnabled : DEFAULT_SITE_PREFS.soundEnabled,
  };
}

export function serializeSitePrefs(prefs: SitePrefs): string {
  return JSON.stringify({ version: SITE_PREFS_VERSION, ...prefs });
}

/** Read prefs; storage that refuses access (e.g. blocked cookies) reads as defaults. */
export function readSitePrefs(storage: PrefsStorage): SitePrefs {
  let raw: string | null;
  try {
    raw = storage.getItem(SITE_PREFS_STORAGE_KEY);
  } catch {
    return DEFAULT_SITE_PREFS;
  }
  return parseSitePrefs(raw);
}

/** Persist prefs (normalized first, so an out-of-range write can't stick). */
export function writeSitePrefs(storage: PrefsStorage, prefs: SitePrefs): SitePrefs {
  const normalized = parseSitePrefs(serializeSitePrefs(prefs));
  storage.setItem(SITE_PREFS_STORAGE_KEY, serializeSitePrefs(normalized));
  return normalized;
}
