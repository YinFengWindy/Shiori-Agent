import type { AffectionStageName, AffectionSummary } from "@yinfengwindy/shiori-sdk";
import { affectionMax, affectionMin, affectionStages } from "./affectionStages";

/** Where `value` sits along the whole -100–100 range, as a 0–100 percentage clamped to the track. */
export function affectionTrackPercent(value: number) {
  const percent = ((value - affectionMin) * 100) / (affectionMax - affectionMin);
  return Math.max(0, Math.min(100, percent));
}

/** One stage's stretch of the track, in percent of its width. */
export type AffectionTrackBand = {
  stage: AffectionStageName;
  start: number;
  width: number;
  /** The stage the value is in. */
  current: boolean;
  /** Below zero: the stages a role dislikes the user in. */
  negative: boolean;
};

/** The overview track's geometry, every position in percent of its width. */
export type AffectionTrack = {
  /** The 7 stages, lowest first; each runs from its own start to the next one's. */
  bands: AffectionTrackBand[];
  /** Stage boundaries drawn as ticks: neither zero (its own center line) nor the floor (its own marker). */
  ticks: number[];
  /** The 0 center line. */
  zero: number;
  /** The current value. */
  marker: number;
  /** The stage floor; null while there is none. */
  floor: number | null;
};

/** Derives the overview track: stage bands, ticks, the 0 line, and value and floor markers. */
export function affectionTrack(summary: AffectionSummary): AffectionTrack {
  const bands = affectionStages.map((stage, index) => {
    const start = affectionTrackPercent(stage.lower);
    const next = affectionStages[index + 1];
    const end = next ? affectionTrackPercent(next.lower) : 100;
    return { stage: stage.name, start, width: end - start, current: stage.name === summary.stage, negative: stage.upper < 0 };
  });
  const zero = affectionTrackPercent(0);
  const floor = typeof summary.floor === "number" ? affectionTrackPercent(summary.floor) : null;
  return {
    bands,
    ticks: bands.slice(1).map((band) => band.start).filter((tick) => tick !== zero && tick !== floor),
    zero,
    marker: affectionTrackPercent(summary.value),
    floor,
  };
}
