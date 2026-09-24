/** Time-of-day phase that picks the site's scene background. */
export type ScenePhase = "day" | "dusk" | "night";

/** First hour of each phase, in the visitor's local time. */
const DAY_START_HOUR = 6;
const DUSK_START_HOUR = 17;
const NIGHT_START_HOUR = 19;

/**
 * The scene phase for a moment in the visitor's local time zone:
 * day 06:00–16:59, dusk 17:00–18:59, night 19:00–05:59.
 */
export function scenePhaseAt(date: Date): ScenePhase {
  const hour = date.getHours();
  if (hour >= DAY_START_HOUR && hour < DUSK_START_HOUR) return "day";
  if (hour >= DUSK_START_HOUR && hour < NIGHT_START_HOUR) return "dusk";
  return "night";
}

