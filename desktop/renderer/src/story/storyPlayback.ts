import type { StoryBeat, StoryDetails } from "./types";

/** Renderer-local cursor for the beat currently being presented to the player. */
export type StoryPlaybackState = {
  storyId: string;
  presentedBeatId: string | null;
  knownBeatIds: string[];
  pendingBeatIds: string[];
  autoPresentedTurnId: string | null;
};

/** Creates a cursor at the latest beat already present when the game page opens. */
export function createStoryPlaybackState(story: StoryDetails): StoryPlaybackState {
  const latestBeat = story.beats.at(-1) ?? null;
  return {
    storyId: story.id,
    presentedBeatId: latestBeat?.id ?? null,
    knownBeatIds: story.beats.map((beat) => beat.id),
    pendingBeatIds: [],
    autoPresentedTurnId: null,
  };
}

/** Synchronizes a local cursor with a new Story read model without skipping committed beats. */
export function syncStoryPlaybackState(state: StoryPlaybackState, story: StoryDetails): StoryPlaybackState {
  if (state.storyId !== story.id) return createStoryPlaybackState(story);

  const beatIds = story.beats.map((beat) => beat.id);
  const beatIdSet = new Set(beatIds);
  const presentedBeatStillExists = state.presentedBeatId === null || beatIdSet.has(state.presentedBeatId);
  if (!presentedBeatStillExists) return createStoryPlaybackState(story);

  const knownBeatIds = new Set(state.knownBeatIds);
  const addedBeats = story.beats.filter((beat) => !knownBeatIds.has(beat.id));
  const pendingBeatIds = state.pendingBeatIds.filter((beatId) => beatIdSet.has(beatId));
  if (addedBeats.length === 0) {
    return pendingBeatIds.length === state.pendingBeatIds.length
      ? { ...state, knownBeatIds: beatIds }
      : { ...state, knownBeatIds: beatIds, pendingBeatIds };
  }

  const previousLatestBeatId = state.knownBeatIds.at(-1) ?? null;
  const isAtPreviouslyKnownLatest = state.presentedBeatId === previousLatestBeatId;
  const firstAddedBeat = addedBeats[0];
  const canAutoPresentBatch = pendingBeatIds.length === 0
    && isAtPreviouslyKnownLatest
    && firstAddedBeat.turnId !== state.autoPresentedTurnId;

  if (!canAutoPresentBatch) {
    return {
      ...state,
      knownBeatIds: beatIds,
      pendingBeatIds: [...pendingBeatIds, ...addedBeats.map((beat) => beat.id).filter((beatId) => !pendingBeatIds.includes(beatId))],
    };
  }

  return {
    ...state,
    knownBeatIds: beatIds,
    presentedBeatId: firstAddedBeat.id,
    pendingBeatIds: addedBeats.slice(1).map((beat) => beat.id),
    autoPresentedTurnId: firstAddedBeat.turnId,
  };
}

/** Returns the beat currently visible in the game surface. */
export function getPresentedStoryBeat(story: StoryDetails, state: StoryPlaybackState): StoryBeat | null {
  return story.beats.find((beat) => beat.id === state.presentedBeatId) ?? null;
}

/** Returns the next committed beat after the local presentation cursor. */
export function getNextStoryBeat(story: StoryDetails, state: StoryPlaybackState): StoryBeat | null {
  const currentIndex = story.beats.findIndex((beat) => beat.id === state.presentedBeatId);
  return currentIndex >= 0 ? story.beats[currentIndex + 1] ?? null : story.beats[0] ?? null;
}

/** Returns whether the player must advance the visible transcript before input is allowed. */
export function hasUnpresentedStoryBeats(story: StoryDetails, state: StoryPlaybackState) {
  return getNextStoryBeat(story, state) !== null;
}

/** Advances the local cursor by exactly one committed beat. */
export function advanceStoryPlayback(story: StoryDetails, state: StoryPlaybackState): StoryPlaybackState {
  const nextBeat = getNextStoryBeat(story, state);
  if (!nextBeat) return state;
  return {
    ...state,
    presentedBeatId: nextBeat.id,
    pendingBeatIds: state.pendingBeatIds.filter((beatId) => beatId !== nextBeat.id),
  };
}
