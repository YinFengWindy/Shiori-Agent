import { useSyncExternalStore } from "react";
import { defaultAppearancePrefs, readAppearancePrefs, writeAppearancePrefs, type AppearancePrefs } from "./appearancePrefs";

/**
 * One in-memory copy of the appearance prefs shared by every subscriber (the
 * settings page and the chat background), backed by localStorage.
 */
let snapshot: AppearancePrefs | null = null;
const listeners = new Set<() => void>();

function getSnapshot(): AppearancePrefs {
  snapshot ??= readAppearancePrefs(window.localStorage);
  return snapshot;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Merges a partial update into the prefs, persists it and notifies subscribers. */
export function updateAppearancePrefs(patch: Partial<AppearancePrefs>): void {
  const current = getSnapshot();
  if (Object.entries(patch).every(([key, value]) => current[key as keyof AppearancePrefs] === value)) return;
  snapshot = writeAppearancePrefs(window.localStorage, { ...current, ...patch });
  listeners.forEach((listener) => listener());
}

/** Forgets the cached copy so the next read comes from storage (tests switch windows between cases). */
export function resetAppearancePrefsCache(): void {
  snapshot = null;
}

/** The current appearance prefs. */
export function useAppearancePrefs(): AppearancePrefs {
  // Static renders (tests) have no storage: they see the defaults.
  return useSyncExternalStore(subscribe, getSnapshot, () => defaultAppearancePrefs);
}
