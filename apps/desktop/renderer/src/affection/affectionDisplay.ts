import type { AffectionSummary } from "@yinfengwindy/shiori-sdk";
import { affectionTrackPercent } from "./affectionTrack";

/** The chat sidebar's affection meter: the stage name and the bar width. */
export type AffectionDisplay = {
  stage: string;
  /** Where the value sits on the whole -100–100 range, as a 0–100 bar width. */
  percent: number;
};

/** Derives the affection meter view; uninitialized or malformed summaries show nothing. */
export function resolveAffectionDisplay(summary: AffectionSummary | null | undefined): AffectionDisplay | null {
  if (!summary || typeof summary.stage !== "string" || !summary.stage) return null;
  const value = Number(summary.value);
  if (!Number.isFinite(value)) return null;
  return { stage: summary.stage, percent: affectionTrackPercent(value) };
}
