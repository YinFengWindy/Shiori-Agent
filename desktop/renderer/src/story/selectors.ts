import type { StoryBeat, StoryDetails, StoryOperation, StorySummary } from "./types";

/** Returns a launcher Story by id without creating a synthetic fallback. */
export function selectStory(stories: StorySummary[], storyId: string) {
  return stories.find((story) => story.storyId === storyId) ?? null;
}

/** Applies the latest Story status to an existing launcher entry. */
export function replaceStorySummary(stories: StorySummary[], story: StoryDetails) {
  const index = stories.findIndex((candidate) => candidate.storyId === story.id);
  if (index < 0) return stories;
  const current = stories[index];
  const currentTimeBand = story.currentTimeBand;
  if (current.title === story.title && current.status === story.status && current.currentTimeBand === currentTimeBand) return stories;
  return stories.map((candidate, candidateIndex) => candidateIndex === index
    ? { ...candidate, title: story.title, status: story.status, currentTimeBand }
    : candidate);
}

/** Maps the current segment operation to the player-facing status. */
export function getStoryStatusLabel(operation: StoryOperation) {
  const labels: Record<StoryOperation, string> = {
    idle: "准备开始",
    awaiting_player: "轮到你了",
    generating: "剧情生成中",
  };
  return labels[operation];
}

/** Returns whether the Story can accept another player input. */
export function canSubmitStoryInput(story: StoryDetails | null) {
  return Boolean(story && story.status === "active" && story.segment.operation === "awaiting_player");
}

/** Merges committed beats idempotently and keeps repository order stable. */
export function mergeStoryBeats(current: StoryBeat[], incoming: StoryBeat[]) {
  if (incoming.length === 0) return current;
  const merged = new Map(current.map((beat) => [beat.id, beat]));
  for (const beat of incoming) merged.set(beat.id, beat);
  const next = [...merged.values()].sort((left, right) => left.sequence - right.sequence);
  if (next.length === current.length && next.every((beat, index) => beat === current[index])) return current;
  return next;
}
