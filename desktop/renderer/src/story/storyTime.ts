import type { StoryDetails } from "./types";

export const STORY_TIME_BANDS = ["清晨", "上午", "下午", "夜晚", "深夜"] as const;
export type StoryTimeBand = (typeof STORY_TIME_BANDS)[number];

/** Validates a player-facing Story period without deriving it from a timestamp. */
export function normalizeStoryTimeBand(value: string): StoryTimeBand | "时间未知" {
  return (STORY_TIME_BANDS as readonly string[]).includes(value as StoryTimeBand)
    ? (value as StoryTimeBand)
    : "时间未知";
}

/** Returns the latest committed period, falling back to the active segment. */
export function getStoryCurrentTimeBand(
  story: Pick<StoryDetails, "beats" | "segment">,
): StoryTimeBand {
  return story.beats[story.beats.length - 1]?.timeBand ?? story.segment.timeBand;
}
