import type { StoryBeat, StoryDetails, StorySummary } from "./types";
import { getStoryCurrentAt } from "./storyTime";

/** Creates a committed Story beat for renderer tests. */
export function createStoryBeat(overrides: Partial<StoryBeat> = {}): StoryBeat {
  return {
    id: overrides.id ?? "beat-1",
    storyId: overrides.storyId ?? "story-1",
    segmentId: overrides.segmentId ?? "segment-1",
    turnId: overrides.turnId ?? "turn-1",
    sequence: overrides.sequence ?? 1,
    effectiveAt: overrides.effectiveAt ?? "2026-08-02T10:00:00+08:00",
    text: overrides.text ?? "你终于来了。",
    kind: overrides.kind ?? "dialogue",
    speaker: overrides.speaker ?? "澪",
    recordedAt: overrides.recordedAt ?? "2026-08-02T10:00:00+08:00",
  };
}

/** Creates the direct Story repository read model used by renderer tests. */
export function createStoryDetails(overrides: Partial<StoryDetails> = {}): StoryDetails {
  return {
    id: overrides.id ?? "story-1",
    title: overrides.title ?? "雨港",
    background: overrides.background ?? "潮汐会带回被遗忘的名字。",
    status: overrides.status ?? "active",
    revision: overrides.revision ?? 1,
    roleSnapshot: overrides.roleSnapshot ?? { id: "role-1", name: "澪" },
    playerProfile: overrides.playerProfile ?? { display_name: "岚", appearance: "短发", identity: "从北方来的抄写员" },
    segment: overrides.segment ?? {
      id: "segment-1",
      sequence: 1,
      startsAt: "2026-08-02T10:00:00+08:00",
      status: "active",
      mode: "plot",
      operation: "awaiting_player",
      openingContext: {},
      runtimeSnapshot: {},
    },
    beats: overrides.beats ?? [createStoryBeat()],
    cues: overrides.cues ?? [],
    turns: overrides.turns ?? [],
  };
}

/** Creates the catalog summary form of a Story. */
export function createStorySummary(story = createStoryDetails()): StorySummary {
  const currentAt = getStoryCurrentAt(story);
  return {
    storyId: story.id,
    relativeDbPath: `${story.id}/story.db`,
    title: story.title,
    status: story.status,
    createdAt: "2026-08-02T10:00:00+08:00",
    currentAt,
  };
}
