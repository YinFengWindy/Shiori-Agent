import type { StoryDetails } from "./types";

const storyHourFormatter = new Intl.DateTimeFormat("en-US", {
  hour: "2-digit",
  hourCycle: "h23",
  timeZone: "Asia/Shanghai",
});

/** Returns the latest committed Story time, falling back to the segment start. */
export function getStoryCurrentAt(story: Pick<StoryDetails, "beats" | "segment">): string {
  return story.beats[story.beats.length - 1]?.effectiveAt ?? story.segment.startsAt;
}

/** Maps a Story timestamp to one of the five player-facing time periods. */
export function getStoryTimeBand(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  const hour = Number(storyHourFormatter.format(date));
  if (hour >= 5 && hour < 9) return "清晨";
  if (hour >= 9 && hour < 12) return "上午";
  if (hour >= 12 && hour < 18) return "下午";
  if (hour >= 18 && hour < 23) return "夜晚";
  return "深夜";
}
