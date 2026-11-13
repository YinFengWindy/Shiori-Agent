import { useSyncExternalStore } from "react";
import { useReducedMotion } from "motion/react";

/** Pace shared by text reveal and auto-play: slower values give the reader more time. */
export type StoryPace = "slow" | "normal" | "fast";

/** Persisted renderer preferences controlling Story playback and presentation. */
export type StoryPreferences = {
  textSpeed: StoryPace;
  showFullText: boolean;
  autoPlay: boolean;
  autoPlaySpeed: StoryPace;
  reducedMotion: boolean;
};

const storageKey = "shiori.story-preferences.v1";

/** Baseline Story preferences used when storage is empty or invalid. */
export const defaultStoryPreferences: StoryPreferences = {
  textSpeed: "normal",
  showFullText: false,
  autoPlay: false,
  autoPlaySpeed: "normal",
  reducedMotion: false,
};

const textCharactersPerSecond: Record<StoryPace, number> = { slow: 18, normal: 36, fast: 72 };
const autoPlayDelayMs: Record<StoryPace, number> = { slow: 2400, normal: 1400, fast: 700 };

/** Characters revealed per second, or null when the whole fragment shows at once. */
export function storyTextCharactersPerSecond(preferences: StoryPreferences): number | null {
  return preferences.showFullText ? null : textCharactersPerSecond[preferences.textSpeed];
}

/** Pause after a fully shown fragment before auto-play moves on. */
export function storyAutoPlayDelayMs(preferences: StoryPreferences): number {
  return autoPlayDelayMs[preferences.autoPlaySpeed];
}

function readPace(value: unknown): StoryPace {
  return value === "slow" || value === "fast" ? value : "normal";
}

/** Reads Story presentation preferences without affecting desktop settings. */
export function readStoryPreferences(): StoryPreferences {
  try {
    const raw = globalThis.localStorage?.getItem(storageKey);
    if (!raw) return defaultStoryPreferences;
    const value = JSON.parse(raw) as Partial<Record<keyof StoryPreferences, unknown>>;
    // Pick known fields only: older builds stored volume and motion-intensity keys that never took effect.
    return {
      textSpeed: readPace(value.textSpeed),
      showFullText: value.showFullText === true,
      autoPlay: value.autoPlay === true,
      autoPlaySpeed: readPace(value.autoPlaySpeed),
      reducedMotion: value.reducedMotion === true,
    };
  } catch {
    return defaultStoryPreferences;
  }
}

let snapshot: StoryPreferences | null = null;
const listeners = new Set<() => void>();

function getSnapshot(): StoryPreferences {
  snapshot ??= readStoryPreferences();
  return snapshot;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** Persists one preference change and notifies every mounted Story surface. */
export function updateStoryPreferences(patch: Partial<StoryPreferences>): void {
  const next = { ...getSnapshot(), ...patch };
  snapshot = next;
  globalThis.localStorage?.setItem(storageKey, JSON.stringify(next));
  for (const listener of listeners) listener();
}

/** Subscribes to the shared Story preferences; the snapshot keeps its identity until a change. */
export function useStoryPreferences(): StoryPreferences {
  return useSyncExternalStore(subscribe, getSnapshot, () => defaultStoryPreferences);
}

/** Whether Story motion should be reduced, by the system setting or the Story preference. */
export function useStoryReducedMotion(): boolean {
  const systemReducedMotion = useReducedMotion() ?? false;
  return useStoryPreferences().reducedMotion || systemReducedMotion;
}
