/**
 * Pure sound decisions for the static site: the volume curve, whether BGM
 * should be playing, and the synthesized SFX recipes. No WebAudio here, so
 * everything is unit-testable; `audioEngine.ts` turns these into nodes.
 */

/** Every sound effect the site plays. */
export type SfxName = "hover" | "click" | "advance" | "open" | "close";

/** One oscillator in a recipe; times are seconds from the trigger. */
export interface SfxVoice {
  readonly wave: "sine" | "triangle";
  readonly frequency: number;
  /** Optional pitch glide target, reached at the end of the release. */
  readonly endFrequency?: number;
  /** Peak linear gain before the SFX volume is applied (kept quiet). */
  readonly peak: number;
  readonly delay: number;
}

/** A short enveloped chord: fast attack, exponential release. */
export interface SfxRecipe {
  readonly voices: readonly SfxVoice[];
  readonly attack: number;
  readonly release: number;
}

/** Quietest audible slider step maps to this attenuation (dB). */
const VOLUME_FLOOR_DB = -40;

/**
 * Map a 0–100 slider value to a linear gain on a decibel curve, so equal
 * slider steps sound like equal loudness steps. 0 is true silence.
 */
export function volumeToGain(volume: number) {
  const clamped = Math.min(100, Math.max(0, volume));
  if (clamped === 0) return 0;
  return 10 ** ((VOLUME_FLOOR_DB * (1 - clamped / 100)) / 20);
}

export interface BgmDecisionInput {
  readonly soundEnabled: boolean;
  /** Configured track URL (`SITE_BGM`), or null when there is none. */
  readonly track: string | null;
  /** An AudioContext exists (created on a user gesture). */
  readonly hasContext: boolean;
}

/** BGM plays only with sound on, a configured track and a live context. */
export function shouldPlayBgm({ soundEnabled, track, hasContext }: BgmDecisionInput) {
  return soundEnabled && track !== null && hasContext;
}

/**
 * Galgame-menu style blips: a barely-there tick on hover, a soft two-note
 * chime on click/confirm, a light bell when the dialogue advances, and a
 * rising / falling pair for opening / closing a modal.
 */
export const SFX_RECIPES: Record<SfxName, SfxRecipe> = {
  hover: {
    voices: [{ wave: "triangle", frequency: 2400, endFrequency: 2100, peak: 0.035, delay: 0 }],
    attack: 0.002,
    release: 0.05,
  },
  click: {
    voices: [
      { wave: "sine", frequency: 1318.5, peak: 0.12, delay: 0 },
      { wave: "sine", frequency: 1975.5, peak: 0.06, delay: 0.045 },
    ],
    attack: 0.004,
    release: 0.32,
  },
  advance: {
    voices: [
      { wave: "sine", frequency: 1046.5, endFrequency: 1108.7, peak: 0.07, delay: 0 },
      { wave: "sine", frequency: 2093, peak: 0.025, delay: 0 },
    ],
    attack: 0.003,
    release: 0.18,
  },
  open: {
    voices: [
      { wave: "sine", frequency: 880, peak: 0.07, delay: 0 },
      { wave: "sine", frequency: 1318.5, peak: 0.07, delay: 0.06 },
    ],
    attack: 0.005,
    release: 0.26,
  },
  close: {
    voices: [
      { wave: "sine", frequency: 1318.5, peak: 0.06, delay: 0 },
      { wave: "sine", frequency: 880, peak: 0.06, delay: 0.06 },
    ],
    attack: 0.005,
    release: 0.22,
  },
};
