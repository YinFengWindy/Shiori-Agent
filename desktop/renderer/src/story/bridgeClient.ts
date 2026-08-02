import { StoryBridgeError, type StoryCreationInput, type StoryDetails, type StorySummary } from "./types";

type DesktopInvoke = typeof window.miraDesktop.invoke;

async function invokePayload<T>(invoke: DesktopInvoke, method: string, payload: Record<string, unknown>) {
  const response = await invoke({ method, payload });
  if (response.error) {
    throw new StoryBridgeError(response.error.message, response.error.code);
  }
  return response.payload as T;
}

/** Typed renderer contract for Story operations. */
export interface StoryBridgeClient {
  listStories(): Promise<StorySummary[]>;
  getStory(storyId: string): Promise<StoryDetails>;
  createStory(input: StoryCreationInput): Promise<StoryDetails>;
  submitInput(storyId: string, input: string, expectedRevision: number): Promise<void>;
  continueStory(storyId: string, expectedRevision: number): Promise<void>;
}

/** Creates a Story client over the constrained desktop bridge. */
export function createStoryBridgeClient(invoke: DesktopInvoke = window.miraDesktop.invoke): StoryBridgeClient {
  return {
    async listStories() {
      return (await invokePayload<{ stories: StorySummary[] }>(invoke, "stories.list", {})).stories;
    },
    async getStory(storyId) {
      return (await invokePayload<{ story: StoryDetails }>(invoke, "stories.get", { story_id: storyId })).story;
    },
    async createStory(input) {
      const payload = await invokePayload<{ story: StoryDetails }>(invoke, "stories.create", {
        title: input.title,
        background: input.background,
        starts_at: input.startsAt,
        role_id: input.roleId,
        player_profile: {
          display_name: input.playerProfile.displayName,
          appearance: input.playerProfile.appearance,
          identity: input.playerProfile.identity,
        },
      });
      return payload.story;
    },
    async submitInput(storyId, input, expectedRevision) {
      await invokePayload(invoke, "stories.input", {
        story_id: storyId,
        input,
        expected_revision: expectedRevision,
      });
    },
    async continueStory(storyId, expectedRevision) {
      await invokePayload(invoke, "stories.continue", {
        story_id: storyId,
        expected_revision: expectedRevision,
      });
    },
  };
}
