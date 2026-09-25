/**
 * Desktop appearance preferences (设置 › 外观). They only change how the
 * renderer draws — nothing the backend or other windows need — so they live
 * in the renderer's localStorage as one versioned JSON value, like the other
 * renderer-side desktop state (`miraDesktop.*`, onboarding progress), rather
 * than in config.toml, whose saves go through the backend runtime.
 *
 * Reading never throws: a missing, corrupt or older value falls back field by
 * field to the defaults.
 */
export type AppearancePrefs = {
  /** Slow breathing + pointer parallax of the chat background portrait. */
  readonly backdropMotion: boolean;
  /** 吟风 (the 看板娘) on the startup splash, empty states, error toasts and 关于. */
  readonly mascot: boolean;
};

/** The subset of `Storage` the prefs need (injectable for tests). */
export type AppearancePrefsStorage = Pick<Storage, "getItem" | "setItem">;

export const appearancePrefsStorageKey = "shiori.desktop.appearance";
const appearancePrefsVersion = 1;

export const defaultAppearancePrefs: AppearancePrefs = {
  backdropMotion: true,
  mascot: true,
};

/** Normalises a stored value into valid prefs, keeping each valid field. */
export function parseAppearancePrefs(raw: string | null): AppearancePrefs {
  if (raw === null) return defaultAppearancePrefs;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return defaultAppearancePrefs;
  }
  if (typeof data !== "object" || data === null) return defaultAppearancePrefs;
  const record = data as Record<string, unknown>;
  if (record.version !== appearancePrefsVersion) return defaultAppearancePrefs;
  return {
    backdropMotion: typeof record.backdropMotion === "boolean" ? record.backdropMotion : defaultAppearancePrefs.backdropMotion,
    // Added after v1 shipped: a stored v1 value without it keeps the default (on).
    mascot: typeof record.mascot === "boolean" ? record.mascot : defaultAppearancePrefs.mascot,
  };
}

/** Reads the prefs from storage. */
export function readAppearancePrefs(storage: AppearancePrefsStorage): AppearancePrefs {
  return parseAppearancePrefs(storage.getItem(appearancePrefsStorageKey));
}

/** Persists the prefs and returns what was stored. */
export function writeAppearancePrefs(storage: AppearancePrefsStorage, prefs: AppearancePrefs): AppearancePrefs {
  const normalized = parseAppearancePrefs(JSON.stringify({ version: appearancePrefsVersion, ...prefs }));
  storage.setItem(appearancePrefsStorageKey, JSON.stringify({ version: appearancePrefsVersion, ...normalized }));
  return normalized;
}
