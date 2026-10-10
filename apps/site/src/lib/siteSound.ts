import bgmUrl from "../assets/audio/bgm.mp3";
import { parseSoundEnabled, serializeSoundPrefs, SITE_PREFS_STORAGE_KEY } from "./sitePrefs";

/*
 * The site's background music switch: one in-memory copy of the visitor's
 * choice (muted by default, persisted by sitePrefs.ts) shared through a
 * tiny external store, and one looping <audio> element. The element — and
 * with it the MP3 download — is only created when the music actually has to
 * play, i.e. after the visitor turns it on.
 *
 * Track: 「Sweet Everyday Moments」, owner-generated, cut at 2:43 so the loop
 * restarts without a gap (from the old galgame site).
 */

/**
 * Playback level: the old site's default BGM volume (60 on its 0–100 slider)
 * through its −40 dB perceptual curve, 10^(−40 × 0.4 / 20) ≈ 0.16.
 */
const BGM_VOLUME = 0.16;

let soundEnabled: boolean | null = null;
let bgm: HTMLAudioElement | null = null;
const listeners = new Set<() => void>();

function readStoredSoundEnabled(): boolean {
  try {
    return parseSoundEnabled(window.localStorage.getItem(SITE_PREFS_STORAGE_KEY));
  } catch {
    // Storage blocked (e.g. cookies disabled): the default, muted.
    return false;
  }
}

function storeSoundEnabled(enabled: boolean) {
  try {
    window.localStorage.setItem(SITE_PREFS_STORAGE_KEY, serializeSoundPrefs(enabled));
  } catch {
    // Storage full or blocked: the choice holds for this visit only.
  }
}

function startBgm() {
  if (!bgm) {
    bgm = new Audio(bgmUrl);
    bgm.loop = true;
    bgm.volume = BGM_VOLUME;
  }
  // A refused play() (autoplay policy, missing file) means the music is not
  // playing: show the switch as off rather than claiming sound.
  bgm.play().catch(() => setSoundEnabled(false));
}

/** Current switch state (`useSyncExternalStore` snapshot). */
export function getSoundEnabled(): boolean {
  soundEnabled ??= readStoredSoundEnabled();
  return soundEnabled;
}

/** Snapshot for the static HTML: the page always ships muted. */
export function getServerSoundEnabled(): boolean {
  return false;
}

/** Subscribe to switch changes; returns the unsubscribe function. */
export function subscribeSound(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Turn the music on or off and remember the choice. Turning it on must
 * happen inside a user gesture (browser autoplay policy).
 */
export function setSoundEnabled(enabled: boolean) {
  if (enabled === getSoundEnabled()) return;
  soundEnabled = enabled;
  storeSoundEnabled(enabled);
  if (enabled) startBgm();
  else bgm?.pause();
  for (const listener of listeners) listener();
}

/**
 * Music left on last visit cannot autoplay: start it on the visitor's first
 * pointer or key press anywhere. Returns a cleanup that drops the listeners.
 */
export function resumeRememberedSoundOnGesture() {
  if (!getSoundEnabled()) return () => {};
  const start = () => {
    remove();
    if (getSoundEnabled()) startBgm();
  };
  function remove() {
    window.removeEventListener("pointerdown", start, true);
    window.removeEventListener("keydown", start, true);
  }
  window.addEventListener("pointerdown", start, true);
  window.addEventListener("keydown", start, true);
  return remove;
}
