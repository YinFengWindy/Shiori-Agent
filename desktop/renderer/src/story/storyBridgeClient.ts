import type { StoryCreationInput, StoryDetails, StorySummary } from "./types";
import { StoryBridgeError } from "./types";

type DesktopInvoke = typeof window.miraDesktop.invoke;

type StorySummaryPayload = {
  story_id: string;
  relative_db_path: string;
  title: string;
  status: "active" | "archived" | "deleting";
  created_at: string;
  current_time_band: StorySummary["currentTimeBand"];
};

type StoryPayload = StoryDetails;

async function invokePayload<T>(invoke: DesktopInvoke, method: string, payload: Record<string, unknown>) {
  const response = await invoke({ method, payload });
  if (response.error) throw new StoryBridgeError(response.error.message, response.error.code);
  return response.payload as T;
}

function toStorySummary(story: StorySummaryPayload): StorySummary {
  return {
    storyId: story.story_id,
    relativeDbPath: story.relative_db_path,
    title: story.title,
    status: story.status,
    createdAt: story.created_at,
    currentTimeBand: story.current_time_band,
  };
}

/** Calls the direct stories.* bridge contract used by the Story surface. */
export interface StoryBridgeClient {
  listStories(): Promise<StorySummary[]>;
  getStory(storyId: string): Promise<StoryDetails>;
  createStory(input: StoryCreationInput): Promise<StoryDetails>;
  submitInput(storyId: string, input: string): Promise<StoryDetails>;
  continueStory(storyId: string): Promise<StoryDetails>;
}

/** Creates the renderer client for the Story simulation bounded context. */
export function createStoryBridgeClient(invoke: DesktopInvoke = window.miraDesktop.invoke): StoryBridgeClient {
  const revisions = new Map<string, number>();

  async function getStory(storyId: string): Promise<StoryDetails> {
    const story = (await invokePayload<{ story: StoryPayload }>(invoke, "stories.get", { story_id: storyId })).story;
    revisions.set(story.id, story.revision);
    return story;
  }

  function rememberStory(story: StoryDetails): StoryDetails {
    revisions.set(story.id, story.revision);
    return story;
  }

  return {
    async listStories() {
      const payload = await invokePayload<{ stories: StorySummaryPayload[] }>(invoke, "stories.list", {});
      return payload.stories.map(toStorySummary);
    },
    getStory,
    async createStory(input) {
      if (!input.roleId) throw new StoryBridgeError("请选择一位角色", "role_required");
      const payload = await invokePayload<{ story: StoryPayload }>(invoke, "stories.create", {
        title: input.title,
        background: input.background,
        time_band: input.timeBand,
        role_id: input.roleId,
        player_profile: {
          display_name: input.playerProfile.displayName,
          appearance: input.playerProfile.appearance,
          identity: input.playerProfile.identity,
        },
      });
      return rememberStory(payload.story);
    },
    async submitInput(storyId, input) {
      const payload = await invokePayload<{ story: StoryPayload }>(invoke, "stories.input", {
        story_id: storyId,
        input,
        expected_revision: revisions.get(storyId) ?? 0,
      });
      return rememberStory(payload.story);
    },
    async continueStory(storyId) {
      const payload = await invokePayload<{ story: StoryPayload }>(invoke, "stories.continue", {
        story_id: storyId,
        expected_revision: revisions.get(storyId) ?? 0,
      });
      return rememberStory(payload.story);
    },
  };
}
