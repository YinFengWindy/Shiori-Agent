import type { ObservationResult } from "./types.js";

export const observationEpisodeMaximumMs = 90 * 60 * 1000;
export const observationEpisodeIdleBoundaryMs = 30 * 60 * 1000;
const observationEpisodeSummaryMaximumChars = 280;

export type ObservationEpisode = {
  index: number;
  activityKey: string;
  startedAt: string;
  happenedAt: string;
  summary: string;
};

export type EpisodeTransition = {
  current: ObservationEpisode | null;
  settled: ObservationEpisode | null;
};

/** Reduces one validated observation into bounded shared-experience episodes. */
export function reduceObservationEpisode(
  current: ObservationEpisode | null,
  result: ObservationResult,
  nextIndex: number,
): EpisodeTransition {
  const candidate = result.experienceCandidate.trim();
  if (!candidate) return { current, settled: null };
  const activityKey = result.activityKey.trim() || "desktop-activity";
  const capturedMs = Date.parse(result.capturedAt);
  const startedMs = current ? Date.parse(current.startedAt) : capturedMs;
  const boundary = Boolean(
    current
    && (
      current.activityKey !== activityKey
      || capturedMs - startedMs >= observationEpisodeMaximumMs
      || capturedMs - Date.parse(current.happenedAt) >= observationEpisodeIdleBoundaryMs
    ),
  );
  const next: ObservationEpisode = {
    index: boundary || !current ? nextIndex : current.index,
    activityKey,
    startedAt: boundary || !current ? result.capturedAt : current.startedAt,
    happenedAt: result.capturedAt,
    summary: boundary || !current ? candidate : mergeEpisodeSummary(current.summary, candidate),
  };
  return { current: next, settled: boundary ? current : null };
}

function mergeEpisodeSummary(current: string, candidate: string): string {
  if (!current || current === candidate) return candidate;
  if (candidate.includes(current)) return candidate.slice(0, observationEpisodeSummaryMaximumChars);
  if (current.includes(candidate)) return current;
  return `${current}；${candidate}`.slice(0, observationEpisodeSummaryMaximumChars);
}
