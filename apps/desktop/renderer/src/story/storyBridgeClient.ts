import type { StoryCgGallery, StoryCreationInput, StoryDetails, StoryResource, StorySummary } from "./types";
import { StoryBridgeError } from "./types";

type DesktopInvoke = typeof window.miraDesktop.invoke;

type StorySummaryPayload = {
  story_id: string;
  relative_db_path: string;
  title: string;
  status: "active" | "archived" | "deleting";
  created_at: string;
  current_story_date: string;
  current_time_band: StorySummary["currentTimeBand"];
  current_scene: { key: string; name: string; character_ids: string[] };
};

type StoryPayload = StoryDetails;

type StoryResourcePayload = StoryResource;

type StoryCgGalleryPayload = {
  story_id: string;
  title: string;
  status: StoryCgGallery["status"];
  created_at: string;
  items: StoryResourcePayload[];
};

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
    currentStoryDate: story.current_story_date,
    currentTimeBand: story.current_time_band,
    currentScene: { key: story.current_scene.key, name: story.current_scene.name, characterIds: story.current_scene.character_ids },
  };
}

/** Calls the direct stories.* bridge contract used by the Story surface. */
export interface StoryBridgeClient {
  listStories(): Promise<StorySummary[]>;
  getStory(storyId: string): Promise<StoryDetails>;
  createStory(input: StoryCreationInput, creationId: string): Promise<StoryDetails>;
  submitInput(storyId: string, input: string): Promise<StoryDetails>;
  continueStory(storyId: string): Promise<StoryDetails>;
  listCgGallery(): Promise<StoryCgGallery[]>;
  retryCg(storyId: string, resourceId: string): Promise<StoryDetails>;
  regenerateCg(storyId: string, resourceId: string): Promise<StoryDetails>;
}

/** Creates the renderer client for the Story simulation bounded context. */
export function createStoryBridgeClient(invoke: DesktopInvoke = window.miraDesktop.invoke): StoryBridgeClient {
  const revisions = new Map<string, number>();
  const latestStories = new Map<string, StoryDetails>();

  async function getStory(storyId: string): Promise<StoryDetails> {
    const story = (await invokePayload<{ story: StoryPayload }>(invoke, "stories.get", { story_id: storyId })).story;
    return rememberStory(story);
  }

  function rememberStory(story: StoryDetails): StoryDetails {
    const latestStory = mergeStoryReadModels(latestStories.get(story.id), story);
    latestStories.set(story.id, latestStory);
    const previousRevision = revisions.get(story.id);
    if (previousRevision === undefined || latestStory.revision > previousRevision) {
      revisions.set(story.id, latestStory.revision);
    }
    return latestStory;
  }

  return {
    async listStories() {
      const payload = await invokePayload<{ stories: StorySummaryPayload[] }>(invoke, "stories.list", {});
      return payload.stories.map(toStorySummary);
    },
    getStory,
    async createStory(input, creationId) {
      if (!input.roleId) throw new StoryBridgeError("请选择一位角色", "role_required");
      const requestPayload: Record<string, unknown> = {
        title: input.title,
        background: input.background,
        story_date: input.storyDate,
        time_band: input.timeBand,
        role_id: input.roleId,
        player_profile: {
          display_name: input.playerProfile.displayName,
          appearance: input.playerProfile.appearance,
          identity: input.playerProfile.identity,
        },
      };
      requestPayload.creation_id = creationId;
      const payload = await invokePayload<{ story: StoryPayload }>(invoke, "stories.create", requestPayload);
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
    async listCgGallery() {
      const payload = await invokePayload<{ stories: StoryCgGalleryPayload[] }>(invoke, "stories.cg.list", {});
      return payload.stories.map((story) => ({
        storyId: story.story_id,
        title: story.title,
        status: story.status,
        createdAt: story.created_at,
        items: story.items,
      }));
    },
    async retryCg(storyId, resourceId) {
      const payload = await invokePayload<{ story: StoryPayload }>(invoke, "stories.cg.retry", {
        story_id: storyId,
        resource_id: resourceId,
      });
      return rememberStory(payload.story);
    },
    async regenerateCg(storyId, resourceId) {
      const payload = await invokePayload<{ story: StoryPayload }>(invoke, "stories.cg.regenerate", {
        story_id: storyId,
        resource_id: resourceId,
      });
      return rememberStory(payload.story);
    },
  };
}

function mergeStoryReadModels(previous: StoryDetails | undefined, incoming: StoryDetails) {
  if (!previous) return incoming;
  const base = incoming.revision >= previous.revision ? incoming : previous;
  const resources = mergeResources(previous.cgGallery, incoming.cgGallery);
  const backgroundResource = resources.find((resource) => resource.kind === "background")
    ?? mergeResource(previous.backgroundResource, incoming.backgroundResource);
  return {
    ...base,
    backgroundResource,
    cgGallery: resources,
  };
}

function mergeResources(previous: StoryResource[], incoming: StoryResource[]) {
  const resources = new Map<string, StoryResource>();
  for (const resource of previous) resources.set(resource.id, resource);
  for (const resource of incoming) {
    resources.set(resource.id, mergeResource(resources.get(resource.id) ?? null, resource) ?? resource);
  }
  return [...resources.values()].sort((left, right) => left.sequence - right.sequence || left.id.localeCompare(right.id));
}

function mergeResource(previous: StoryResource | null, incoming: StoryResource | null) {
  if (!previous) return incoming;
  if (!incoming) return previous;
  const previousTime = Date.parse(previous.updatedAt);
  const incomingTime = Date.parse(incoming.updatedAt);
  return incomingTime > previousTime ? incoming : previous;
}
