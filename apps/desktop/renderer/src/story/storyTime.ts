import type { StoryDetails } from "./types";

/** Player-facing Story periods accepted by creation and runtime read models. */
export const STORY_TIME_BANDS = ["清晨", "上午", "下午", "夜晚", "深夜"] as const;

/** Union of valid player-facing Story period labels. */
export type StoryTimeBand = (typeof STORY_TIME_BANDS)[number];

/** Formats the persisted Story calendar date without consulting the system clock. */
export function formatStoryDate(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
  if (!match) return "日期未知";
  return `${Number(match[1])}年${Number(match[2])}月${Number(match[3])}日`;
}

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
