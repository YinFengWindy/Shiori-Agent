import type { AffectionSummary } from "@yinfengwindy/shiori-sdk";

/** The affection meter's view (chat sidebar, role affection tab): the stage name and the bar width. */
export type AffectionDisplay = {
  stage: string;
  /** Progress within the current stage as a 0–100 bar width. */
  percent: number;
};

/** Derives the affection meter view; uninitialized or malformed summaries show nothing. */
export function resolveAffectionDisplay(summary: AffectionSummary | null | undefined): AffectionDisplay | null {
  if (!summary || typeof summary.stage !== "string" || !summary.stage) return null;
  const progress = Number(summary.progress);
  if (!Number.isFinite(progress)) return null;
  return { stage: summary.stage, percent: Math.max(0, Math.min(1, progress)) * 100 };
}
