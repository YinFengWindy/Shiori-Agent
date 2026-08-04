import type { StoryBeat, StoryDetails, StoryTurn } from "./types";
import { formatStoryDate, normalizeStoryTimeBand, type StoryTimeBand } from "./storyTime";

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

type StoryArchiveTimelineItem = StoryArchiveEntry & {
  storyDate: string;
  timeBand: StoryArchivePeriod["timeBand"];
  order: number;
};

/** Groups committed beats and their player inputs into date and time-period sections. */
export function buildStoryArchiveDays(story: Pick<StoryDetails, "beats" | "turns">): StoryArchiveDay[] {
  const beatsById = new Map(story.beats.map((beat) => [beat.id, beat]));
  const beatItems = story.beats.map((beat) => createBeatTimelineItem(beat));
  const playerItems = story.turns.flatMap((turn) => {
    const item = createPlayerTimelineItem(turn, beatsById);
    return item ? [item] : [];
  });
  const timeline = [...beatItems, ...playerItems].sort(compareTimelineItems);
  const days: StoryArchiveDay[] = [];
  const dayMap = new Map<string, StoryArchiveDay>();
  const periodsByDay = new Map<string, Map<StoryArchivePeriod["timeBand"], StoryArchivePeriod>>();

  for (const item of timeline) {
    const date = resolveArchiveDate(item.storyDate);
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

function createBeatTimelineItem(beat: StoryBeat): StoryArchiveTimelineItem {
  if (beat.kind === "dialogue") {
    return {
      id: `beat:${beat.id}`,
      kind: "dialogue",
      label: beat.speaker || "角色",
      text: beat.text,
      storyDate: beat.storyDate,
      timeBand: normalizeStoryTimeBand(beat.timeBand),
      order: beat.sequence * 2 + 1,
    };
  }
  return {
    id: `beat:${beat.id}`,
    kind: "narration",
    label: "旁白",
    text: beat.text,
    storyDate: beat.storyDate,
    timeBand: normalizeStoryTimeBand(beat.timeBand),
    order: beat.sequence * 2 + 1,
  };
}

function createPlayerTimelineItem(
  turn: StoryTurn,
  beatsById: Map<string, StoryBeat>,
): StoryArchiveTimelineItem | null {
  if ((turn.kind !== "player" && turn.kind !== "continue") || !turn.input.trim()) return null;
  const firstCommittedBeat = turn.committedBeatIds.map((beatId) => beatsById.get(beatId)).find(Boolean);
  if (!firstCommittedBeat) return null;
  return {
    id: `turn:${turn.id}`,
    kind: "player",
    label: "玩家",
    text: turn.input,
    storyDate: firstCommittedBeat.storyDate,
    timeBand: normalizeStoryTimeBand(firstCommittedBeat.timeBand),
    order: firstCommittedBeat.sequence * 2,
  };
}

function compareTimelineItems(left: StoryArchiveTimelineItem, right: StoryArchiveTimelineItem): number {
  return left.order - right.order;
}

function resolveArchiveDate(value: string): { key: string; label: string } {
  const label = formatStoryDate(value);
  if (label === "日期未知") return { key: "unknown", label };
  const [year, month, day] = value.split("-");
  return {
    key: `${year}-${month}-${day}`,
    label,
  };
}
