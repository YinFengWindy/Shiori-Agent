import type { AffectionStageName } from "@yinfengwindy/shiori-sdk";

/** The lowest affection value. */
export const affectionMin = -100;
/** The highest affection value. */
export const affectionMax = 100;

/** One fixed affection stage; `lower` and `upper` are both inclusive. */
export type AffectionStageBounds = { name: AffectionStageName; lower: number; upper: number };

/**
 * The fixed stages, lowest first. Mirrors `AFFECTION_STAGES` in
 * `apps/backend/core/roles/relationship_runtime/affection.py`;
 * `affectionStages.test.ts` reads that file to keep the two in step.
 */
export const affectionStages: readonly AffectionStageBounds[] = [
  { name: "厌恶", lower: -100, upper: -50 },
  { name: "冷淡", lower: -49, upper: -1 },
  { name: "陌生", lower: 0, upper: 19 },
  { name: "熟悉", lower: 20, upper: 39 },
  { name: "朋友", lower: 40, upper: 59 },
  { name: "亲密", lower: 60, upper: 79 },
  { name: "挚爱", lower: 80, upper: 100 },
];

/** The stage of 0, where a role without affection would start: 「陌生」. */
export const neutralAffectionStage: AffectionStageName = "陌生";
