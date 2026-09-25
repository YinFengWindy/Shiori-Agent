/**
 * When the startup splash (吟风 over the time-of-day scene while the local
 * backend boots) is on screen, and what it says. Pure so the timing gate is
 * testable; `useStartupSplash` feeds it the clock.
 */

/** A quicker startup never shows the splash, so it cannot flash for a frame. */
export const startupSplashDelayMs = 400;

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
  /** Time since the current connection attempt began. */
  attemptElapsedMs: number;
};

/**
 * The splash phase, or null when no splash is due. Only the first connect
 * after launch counts: once the backend has answered, later drops are the
 * offline banner's job. A failed startup shows at once (it does not go away
 * by itself); a booting one only after `startupSplashDelayMs`, unless the
 * splash is already up, e.g. while it retries after 「重启连接」.
 */
export function selectStartupSplashPhase({ health, settled, shown, attemptElapsedMs }: StartupSplashInput): StartupSplashPhase | null {
  if (settled || health === "online") return null;
  if (health === "offline") return "failed";
  if (!shown && attemptElapsedMs < startupSplashDelayMs) return null;
  return attemptElapsedMs >= startupSlowAfterMs ? "slow" : "booting";
}

/** The next elapsed time at which the phase can change by itself, or null once nothing is pending. */
export function nextStartupSplashCheckMs(attemptElapsedMs: number): number | null {
  if (attemptElapsedMs < startupSplashDelayMs) return startupSplashDelayMs;
  if (attemptElapsedMs < startupSlowAfterMs) return startupSlowAfterMs;
  return null;
}
