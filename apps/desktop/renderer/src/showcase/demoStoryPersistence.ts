import type { StoryDetails, StoryTurn } from "../../../../../plugins/story/ui/types";
import { STORY_TIME_BANDS } from "../../../../../plugins/story/ui/storyTime";
import { appendDemoStoryTurn, createDemoStory } from "./demoStoryModel";
import { storyChapters } from "./demoStoryChapters";
import { readDemoStorage, type DemoStorage } from "./demoStorage";

type SavedStory = Pick<StoryDetails, "id" | "title" | "background" | "playerProfile" | "currentStoryDate" | "currentTimeBand"> & {
  turns: Array<Pick<StoryTurn, "kind" | "input">>;
  openingTimeBand?: StoryDetails["currentTimeBand"];
};

/** Only save visitor inputs and sample progress; reconstruct trusted assets and read models. */
export const demoStoriesStorageKey = "shiori-showcase.stories.v1";

function isSavedStory(value: unknown): value is SavedStory {
  if (!value || typeof value !== "object") return false;
  if (!("id" in value) || typeof value.id !== "string" || !value.id.startsWith("demo-")) return false;
  if (!("title" in value) || typeof value.title !== "string" || !("background" in value) || typeof value.background !== "string") return false;
  if (!("currentStoryDate" in value) || typeof value.currentStoryDate !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value.currentStoryDate)) return false;
  if (!("currentTimeBand" in value) || !STORY_TIME_BANDS.some((band) => band === value.currentTimeBand)) return false;
  if ("openingTimeBand" in value && !STORY_TIME_BANDS.some((band) => band === value.openingTimeBand)) return false;
  if (!("playerProfile" in value) || !value.playerProfile || typeof value.playerProfile !== "object") return false;
  const profile = value.playerProfile;
  if (!("display_name" in profile) || typeof profile.display_name !== "string" || !("identity" in profile) || typeof profile.identity !== "string" || !("appearance" in profile) || typeof profile.appearance !== "string") return false;
  return "turns" in value && Array.isArray(value.turns) && value.turns.length > 0 && value.turns.length <= storyChapters.length
    && value.turns.every((turn: unknown, index) => !!turn && typeof turn === "object" && "input" in turn && typeof turn.input === "string" && "kind" in turn
      && (index === 0 ? turn.kind === "opening" : turn.kind === "player" || turn.kind === "continue"));
}

/** Reject malformed storage instead of passing partially validated objects to Story views. */
export function restoreDemoStories(storage: DemoStorage) {
  const saved = readDemoStorage(storage, demoStoriesStorageKey, (value): value is SavedStory[] => Array.isArray(value) && value.length <= 12 && value.every(isSavedStory));
  if (!saved) return [createDemoStory()];
  return saved.map((entry) => {
    let story = createDemoStory({ creation_id: entry.id.slice(5), title: entry.title, background: entry.background, story_date: entry.currentStoryDate, time_band: entry.openingTimeBand ?? entry.currentTimeBand, player_profile: entry.playerProfile });
    for (const turn of entry.turns.slice(1)) story = appendDemoStoryTurn(story, turn.input, turn.kind);
    return story;
  });
}

/** Write only the small fixture replay recipe, never trust serialized asset URLs. */
export function persistDemoStories(storage: DemoStorage, stories: Iterable<StoryDetails>) {
  const saved: SavedStory[] = [...stories].map(({ id, title, background, playerProfile, currentStoryDate, currentTimeBand, turns, beats }) => ({
    id, title, background, playerProfile, currentStoryDate, currentTimeBand, openingTimeBand: beats[0]?.timeBand ?? currentTimeBand, turns: turns.map(({ kind, input }) => ({ kind, input })),
  }));
  storage.setItem(demoStoriesStorageKey, JSON.stringify(saved));
}
