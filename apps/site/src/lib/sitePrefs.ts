/**
 * The visitor's sound preference, persisted as the old galgame site's
 * versioned JSON value (`shiori-site-prefs`, version 1) so a returning
 * visitor keeps the choice they made there. Only `soundEnabled` is still
 * read; the site starts muted unless a valid stored value says otherwise.
 */

/** localStorage key, shared with the old site. */
export const SITE_PREFS_STORAGE_KEY = "shiori-site-prefs";
const SITE_PREFS_VERSION = 1;

/**
 * Whether sound was left on. A missing, corrupt or wrong-version value reads
 * as muted, because the visitor's storage is outside our control.
 */
export function parseSoundEnabled(raw: string | null): boolean {
  if (raw === null) return false;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return false;
  }
  if (typeof data !== "object" || data === null) return false;
  const record = data as Record<string, unknown>;
  return record.version === SITE_PREFS_VERSION && record.soundEnabled === true;
}

/** The stored value for `soundEnabled`. */
export function serializeSoundPrefs(soundEnabled: boolean): string {
  return JSON.stringify({ version: SITE_PREFS_VERSION, soundEnabled });
}
