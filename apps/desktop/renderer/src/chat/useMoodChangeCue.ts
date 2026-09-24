import { useEffect, useRef, useState } from "react";
import { observeMood, type MoodCueTracker } from "./moodChangeCue";
import { moodTone, type MoodTone } from "./moodTone";

/** One mood change to perform; `id` grows with every real change. */
export type MoodChangeCue = { id: number; tone: MoodTone };

type UseMoodChangeCueArgs = {
  /** Role + session the mood belongs to; a new scope resets the baseline. */
  scope: string;
  mood: string;
  /** The session's `current_mood_updated_at`. */
  updatedAt: string;
};

/**
 * Emits a cue for each real mood change seen while mounted (see
 * `moodChangeCue.ts` for what counts); the first mood after mounting never
 * plays.
 */
export function useMoodChangeCue({ scope, mood, updatedAt }: UseMoodChangeCueArgs) {
  const trackerRef = useRef<MoodCueTracker | null>(null);
  const [cue, setCue] = useState<MoodChangeCue | null>(null);

  useEffect(() => {
    const { tracker, play } = observeMood(trackerRef.current, { scope, mood, updatedAt, now: Date.now() });
    trackerRef.current = tracker;
    if (play) setCue((current) => ({ id: (current?.id ?? 0) + 1, tone: moodTone(mood) }));
  }, [scope, mood, updatedAt]);

  return cue;
}
