import type { StoryBeat, StoryDetails, StoryTurn } from "./types";
import { normalizeStoryTimeBand, type StoryTimeBand } from "./storyTime";

/** The three player-facing entry types used by the Story archive. */
export type StoryArchiveEntryKind = "narration" | "dialogue" | "player";

/** One archive entry after Story beats and player turns are merged. */
export type StoryArchiveEntry = {
  id: string;
  kind: StoryArchiveEntryKind;
  label: string;
  text: string;
};

/** One time-period section within a calendar day. */
export type StoryArchivePeriod = {
  timeBand: StoryTimeBand | "时间未知";
  entries: StoryArchiveEntry[];
};

/** One calendar-day section rendered by the Story archive surface. */
export type StoryArchiveDay = {
  key: string;
  label: string;
  periods: StoryArchivePeriod[];
};

const archiveDateFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "numeric",
  day: "numeric",
});

type StoryArchiveTimelineItem = StoryArchiveEntry & {
  timeBand: StoryArchivePeriod["timeBand"];
  recordedAt: string;
  order: number;
};

/** Groups committed beats and their player inputs into date and time-period sections. */
export function buildStoryArchiveDays(story: Pick<StoryDetails, "beats" | "turns">): StoryArchiveDay[] {
  const beatsById = new Map(story.beats.map((beat) => [beat.id, beat]));
  const beatItems = story.beats.map((beat, order) => createBeatTimelineItem(beat, order));
  const playerItems = story.turns.flatMap((turn, order) => {
    const item = createPlayerTimelineItem(turn, beatsById, story.beats.length + order);
    return item ? [item] : [];
  });
  const timeline = [...beatItems, ...playerItems].sort(compareTimelineItems);
  const days: StoryArchiveDay[] = [];
  const dayMap = new Map<string, StoryArchiveDay>();
  const periodsByDay = new Map<string, Map<StoryArchivePeriod["timeBand"], StoryArchivePeriod>>();

  for (const item of timeline) {
    const date = resolveArchiveDate(item.recordedAt);
    let day = dayMap.get(date.key);
    if (!day) {
      day = { key: date.key, label: date.label, periods: [] };
      dayMap.set(date.key, day);
      days.push(day);
    }

    let periods = periodsByDay.get(date.key);
    if (!periods) {
      periods = new Map();
      periodsByDay.set(date.key, periods);
    }
    let period = periods.get(item.timeBand);
    if (!period) {
      period = { timeBand: item.timeBand, entries: [] };
      periods.set(item.timeBand, period);
      day.periods.push(period);
    }
    period.entries.push({ id: item.id, kind: item.kind, label: item.label, text: item.text });
  }

  return days;
}

function createBeatTimelineItem(beat: StoryBeat, order: number): StoryArchiveTimelineItem {
  if (beat.kind === "dialogue") {
    return {
      id: `beat:${beat.id}`,
      kind: "dialogue",
      label: beat.speaker || "角色",
      text: beat.text,
      timeBand: normalizeStoryTimeBand(beat.timeBand),
      recordedAt: beat.recordedAt,
      order,
    };
  }
  return {
    id: `beat:${beat.id}`,
    kind: "narration",
    label: "旁白",
    text: beat.text,
    timeBand: normalizeStoryTimeBand(beat.timeBand),
    recordedAt: beat.recordedAt,
    order,
  };
}

function createPlayerTimelineItem(
  turn: StoryTurn,
  beatsById: Map<string, StoryBeat>,
  order: number,
): StoryArchiveTimelineItem | null {
  if ((turn.kind !== "player" && turn.kind !== "continue") || !turn.input.trim()) return null;
  const firstCommittedBeat = turn.committedBeatIds.map((beatId) => beatsById.get(beatId)).find(Boolean);
  if (!firstCommittedBeat) return null;
  return {
    id: `turn:${turn.id}`,
    kind: "player",
    label: "玩家",
    text: turn.input,
    timeBand: normalizeStoryTimeBand(firstCommittedBeat.timeBand),
    recordedAt: turn.createdAt,
    order,
  };
}

function compareTimelineItems(left: StoryArchiveTimelineItem, right: StoryArchiveTimelineItem): number {
  const timestampDelta = parseTimestamp(left.recordedAt) - parseTimestamp(right.recordedAt);
  return timestampDelta || left.order - right.order;
}

function parseTimestamp(value: string): number {
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? Number.MAX_SAFE_INTEGER : timestamp;
}

function resolveArchiveDate(value: string): { key: string; label: string } {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return { key: "unknown", label: "日期未知" };
  const parts = archiveDateFormatter.formatToParts(date).reduce<Record<string, string>>((result, part) => {
    if (part.type !== "literal") result[part.type] = part.value;
    return result;
  }, {});
  const year = parts.year ?? "未知";
  const month = parts.month ?? "未知";
  const day = parts.day ?? "未知";
  return {
    key: `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`,
    label: `${year}年${month}月${day}日`,
  };
}
