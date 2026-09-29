/**
 * When the startup splash (吟风 over the time-of-day scene while the local
 * backend boots) is on screen, and what it says. Pure so the timing gate is
 * testable; `useStartupSplash` feeds it the clock.
 */

/** On first launch the splash stays up at least this long (not counting its fade-out). */
export const startupSplashMinMs = 3000;

/** From here on 吟风 remarks that startup is slow. */
export const startupSlowAfterMs = 8000;

/** How long the splash fades out once the backend answers; matches `--duration-base`. */
export const startupSplashExitMs = 220;

/**
 * - `booting`: the backend is starting (a time-of-day greeting);
 * - `slow`: still starting after `startupSlowAfterMs`;
 * - `failed`: it did not come up; the splash offers 「重启连接」.
 */
export type StartupSplashPhase = "booting" | "slow" | "failed";

export type StartupSplashInput = {
  /** Bridge health: "connecting" / "online" / "offline". */
  health: string;
  /** The backend has answered at least once since launch: startup is over for good. */
  settled: boolean;
  /** The splash is already up (it stays up across a restart from its own button). */
  shown: boolean;
  /** The current attempt is the one begun at launch, not a 「重启连接」 after a failure. */
  firstAttempt: boolean;
  /** Time since the current connection attempt began (since launch on the first attempt). */
  attemptElapsedMs: number;
};

/**
 * The splash phase, or null when no splash is due. Only the first connect
 * after launch counts: once the backend has answered, later drops are the
 * offline banner's job. The splash shows at once, and a failed startup
 * turns it to `failed` (it does not go away by itself). On the first
 * attempt a splash already up is held until `startupSplashMinMs` after
 * launch even if the backend answered sooner; a slower answer, or one
 * after 「重启连接」, lets it go at once.
 */
export function selectStartupSplashPhase({ health, settled, shown, firstAttempt, attemptElapsedMs }: StartupSplashInput): StartupSplashPhase | null {
  if (settled || health === "online") {
    return shown && firstAttempt && attemptElapsedMs < startupSplashMinMs ? "booting" : null;
  }
  if (health === "offline") return "failed";
  return attemptElapsedMs >= startupSlowAfterMs ? "slow" : "booting";
}

/**
 * The next elapsed time at which the phase can change by itself (the
 * minimum-duration floor, then the slow remark), or null once nothing is pending.
 */
export function nextStartupSplashCheckMs(attemptElapsedMs: number, settled: boolean): number | null {
  if (attemptElapsedMs < startupSplashMinMs) return startupSplashMinMs;
  if (!settled && attemptElapsedMs < startupSlowAfterMs) return startupSlowAfterMs;
  return null;
}
