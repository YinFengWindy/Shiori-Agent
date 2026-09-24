/**
 * Decides when a mood change deserves the mood-change performance (portrait
 * flourish, pill pop, particle burst). Only a change that happens while the
 * user is looking counts: the first mood seen after mounting, a role or
 * session switch, and a reload that brings back a mood set earlier all just
 * move the baseline.
 *
 * "Happens while looking" is judged with the session's
 * `current_mood_updated_at` stamp: the new mood must have been set at or
 * after the moment the current role/session came into view. A cached session
 * replaced by its freshly fetched copy on a role switch carries a mood that
 * was set before the switch, so it does not play.
 */
export type MoodCueTracker = {
  /** Role + session the baseline belongs to. */
  scope: string;
  mood: string;
  /** When this scope came into view (ms since epoch). */
  since: number;
};

export type MoodObservation = {
  scope: string;
  mood: string;
  /** The session's `current_mood_updated_at` (ISO), empty when the mood is a fallback. */
  updatedAt: string;
  /** Now, in ms since epoch. */
  now: number;
};

/**
 * Folds one observation into the tracker. `play` is true only for a real
 * change of a non-empty mood in the same scope, stamped at or after the
 * scope came into view.
 */
export function observeMood(tracker: MoodCueTracker | null, observation: MoodObservation): { tracker: MoodCueTracker; play: boolean } {
  const { scope, mood, updatedAt, now } = observation;
  if (!tracker || tracker.scope !== scope) {
    return { tracker: { scope, mood, since: now }, play: false };
  }
  if (tracker.mood === mood) return { tracker, play: false };
  const stamp = Date.parse(updatedAt);
  const play = Boolean(mood) && Number.isFinite(stamp) && stamp >= tracker.since;
  return { tracker: { ...tracker, mood }, play };
}
