import { createContext, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { SITE_BGM } from "../content/siteBgm";
import type { SitePrefs } from "../prefs/sitePrefs";
import { useSitePrefs } from "../prefs/useSitePrefs";
import { createAudioEngine, type SoundSettings } from "./audioEngine";
import type { SfxName } from "./soundModel";

/** What components get from `useSound()`. */
export interface SoundApi {
  readonly soundEnabled: boolean;
  /** Flip the master switch; must be called from a user gesture (it may create the AudioContext). */
  readonly toggleSound: () => void;
  readonly playSfx: (name: SfxName) => void;
  /** Throttled sample blip at `volume`, for the SFX volume slider. */
  readonly previewSfx: (volume: number) => void;
}

export const SoundContext = createContext<SoundApi | null>(null);

/** Minimum gap between slider preview blips, so dragging doesn't buzz. */
const PREVIEW_INTERVAL_MS = 90;

function soundSettings(prefs: SitePrefs, soundEnabled = prefs.soundEnabled): SoundSettings {
  return { soundEnabled, sfxVolume: prefs.sfxVolume, bgmVolume: prefs.bgmVolume, track: SITE_BGM };
}

/**
 * Owns the site's one audio engine and keeps it in step with the visitor's
 * prefs (toggle, volumes — live). Nothing is created or played before a
 * user gesture: the toggle click unlocks audio, and if sound was left on
 * last visit the first pointer/key press anywhere unlocks it.
 */
export function SoundProvider({ children }: { children: ReactNode }) {
  const { prefs, update } = useSitePrefs();
  const [engine] = useState(() => createAudioEngine());
  const lastPreviewRef = useRef(0);

  useEffect(() => {
    engine.sync(soundSettings(prefs));
  }, [engine, prefs]);

  // Sound remembered as on: wait for the first gesture to create the context.
  useEffect(() => {
    if (!prefs.soundEnabled || engine.unlocked) return;
    const unlock = () => {
      engine.unlock();
      remove();
    };
    function remove() {
      window.removeEventListener("pointerdown", unlock, true);
      window.removeEventListener("keydown", unlock, true);
    }
    window.addEventListener("pointerdown", unlock, true);
    window.addEventListener("keydown", unlock, true);
    return remove;
  }, [engine, prefs.soundEnabled]);

  const toggleSound = useCallback(() => {
    const enabling = !prefs.soundEnabled;
    // Apply before the prefs round-trip so the confirm chime can play now.
    engine.sync(soundSettings(prefs, enabling));
    if (enabling) {
      engine.unlock();
      engine.playSfx("click");
    }
    update({ soundEnabled: enabling });
  }, [engine, prefs, update]);

  const previewSfx = useCallback(
    (volume: number) => {
      const now = performance.now();
      if (now - lastPreviewRef.current < PREVIEW_INTERVAL_MS) return;
      lastPreviewRef.current = now;
      engine.setSfxVolume(volume);
      engine.playSfx("click");
    },
    [engine],
  );

  const api = useMemo<SoundApi>(
    () => ({ soundEnabled: prefs.soundEnabled, toggleSound, playSfx: engine.playSfx, previewSfx }),
    [prefs.soundEnabled, toggleSound, engine, previewSfx],
  );

  return <SoundContext.Provider value={api}>{children}</SoundContext.Provider>;
}
