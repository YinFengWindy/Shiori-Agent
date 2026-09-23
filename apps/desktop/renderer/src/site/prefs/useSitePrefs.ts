import { useCallback, useSyncExternalStore } from "react";
import { readSitePrefs, writeSitePrefs, type SitePrefs } from "./sitePrefs";

/**
 * One in-memory copy of the visitor's prefs shared by every component
 * (settings modal, ADV screen, and the sound ticket #349), backed by
 * localStorage. Components subscribe with `useSitePrefs()`.
 */
let snapshot: SitePrefs | null = null;
const listeners = new Set<() => void>();

function getSnapshot(): SitePrefs {
  snapshot ??= readSitePrefs(window.localStorage);
  return snapshot;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Merge a partial update into the prefs, persist it, and notify subscribers. */
export function updateSitePrefs(patch: Partial<SitePrefs>) {
  const next = { ...getSnapshot(), ...patch };
  try {
    snapshot = writeSitePrefs(window.localStorage, next);
  } catch {
    // Storage full or blocked: keep the change for this visit only.
    snapshot = next;
  }
  listeners.forEach((listener) => listener());
}

/** Current prefs plus a stable `update(patch)` setter. */
export function useSitePrefs() {
  const prefs = useSyncExternalStore(subscribe, getSnapshot);
  const update = useCallback((patch: Partial<SitePrefs>) => updateSitePrefs(patch), []);
  return { prefs, update };
}
