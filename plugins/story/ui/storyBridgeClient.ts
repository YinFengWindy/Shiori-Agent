import { rpcMethods, type RpcMethod } from "../rpcMethods.generated";
import { PluginBridgeError, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { PluginServiceReference } from "@yinfengwindy/shiori-sdk";
import type { StoryCgGallery, StoryCreationInput, StoryDetails, StoryResource, StorySummary, StoryVoice, StoryVoiceAudio } from "./types";
import { StoryBridgeError } from "./types";

type StorySummaryPayload = {
  story_id: string;
  relative_db_path: string;
  title: string;
  status: "active" | "archived" | "deleting";
  created_at: string;
  current_story_date: string;
  current_time_band: StorySummary["currentTimeBand"];
  current_scene: { key: string; name: string; character_ids: string[] };
  role_id: string;
  role_name: string;
  cover_path: string | null;
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

async function invokePayload<T>(client: PluginRpcClient, method: RpcMethod, payload: Record<string, unknown>): Promise<T> {
  try {
    return await client.call<T>(method, payload);
  } catch (error) {
    if (error instanceof PluginBridgeError) throw new StoryBridgeError(error.message, error.code, error.details);
    throw error;
  }
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
    roleId: story.role_id,
    roleName: story.role_name,
    coverPath: story.cover_path,
  };
}

/** Calls the direct stories.* bridge contract used by the Story surface. */
export interface StoryBridgeClient {
  listStories(): Promise<StorySummary[]>;
  getStory(storyId: string): Promise<StoryDetails>;
  renameStory(storyId: string, title: string): Promise<StorySummary>;
  deleteStory(storyId: string): Promise<void>;
  createStory(input: StoryCreationInput, creationId: string): Promise<StoryDetails>;
  submitInput(storyId: string, input: string): Promise<StoryDetails>;
  continueStory(storyId: string): Promise<StoryDetails>;
  listCgGallery(): Promise<StoryCgGallery[]>;
  retryCg(storyId: string, resourceId: string): Promise<StoryDetails>;
  regenerateCg(storyId: string, resourceId: string): Promise<StoryDetails>;
  /** Reads one saved voice line, or null when it was never saved or its file is gone. */
  getVoice(storyId: string, beatId: string, fragmentIndex: number): Promise<(StoryVoice & StoryVoiceAudio) | null>;
  /** Saves synthesized audio for one dialogue fragment into the Story. */
  saveVoice(storyId: string, beatId: string, fragmentIndex: number, provider: PluginServiceReference, audio: StoryVoiceAudio): Promise<StoryVoice>;
}

/** Creates the renderer client for the Story simulation bounded context. */
export function createStoryBridgeClient(client: PluginRpcClient): StoryBridgeClient {
  const revisions = new Map<string, number>();
  const latestStories = new Map<string, StoryDetails>();

  async function getStory(storyId: string): Promise<StoryDetails> {
    const story = (await invokePayload<{ story: StoryPayload }>(client, rpcMethods["get"], { story_id: storyId })).story;
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
      const payload = await invokePayload<{ stories: StorySummaryPayload[] }>(client, rpcMethods["list"], {});
      return payload.stories.map(toStorySummary);
    },
    getStory,
    async renameStory(storyId, title) {
      const payload = await invokePayload<{ story: StorySummaryPayload }>(client, rpcMethods["rename"], { story_id: storyId, title });
      const latestStory = latestStories.get(storyId);
      if (latestStory) latestStories.set(storyId, { ...latestStory, title: payload.story.title });
      return toStorySummary(payload.story);
    },
    async deleteStory(storyId) {
      await invokePayload<{ story_id: string }>(client, rpcMethods["delete"], { story_id: storyId });
      latestStories.delete(storyId);
      revisions.delete(storyId);
    },
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
      const payload = await invokePayload<{ story: StoryPayload }>(client, rpcMethods["create"], requestPayload);
      return rememberStory(payload.story);
    },
    async submitInput(storyId, input) {
      const payload = await invokePayload<{ story: StoryPayload }>(client, rpcMethods["input"], {
        story_id: storyId,
        input,
        expected_revision: revisions.get(storyId) ?? 0,
      });
      return rememberStory(payload.story);
    },
    async continueStory(storyId) {
      const payload = await invokePayload<{ story: StoryPayload }>(client, rpcMethods["continue"], {
        story_id: storyId,
        expected_revision: revisions.get(storyId) ?? 0,
      });
      return rememberStory(payload.story);
    },
    async getVoice(storyId, beatId, fragmentIndex) {
      const payload = await invokePayload<{ voice: (StoryVoice & StoryVoiceAudio) | null }>(client, rpcMethods["voice.get"], { story_id: storyId, beat_id: beatId, fragment_index: fragmentIndex });
      return payload.voice;
    },
    async saveVoice(storyId, beatId, fragmentIndex, provider, audio) {
      const payload = await invokePayload<{ voice: StoryVoice }>(client, rpcMethods["voice.save"], {
        story_id: storyId,
        beat_id: beatId,
        fragment_index: fragmentIndex,
        provider,
        audio_base64: audio.audio_base64,
        format: audio.format,
      });
      const latestStory = latestStories.get(storyId);
      if (latestStory) latestStories.set(storyId, { ...latestStory, voices: mergeVoices(latestStory.voices, [payload.voice]) });
      return payload.voice;
    },
    async listCgGallery() {
      const payload = await invokePayload<{ stories: StoryCgGalleryPayload[] }>(client, rpcMethods["cg.list"], {});
      return payload.stories.map((story) => ({
        storyId: story.story_id,
        title: story.title,
        status: story.status,
        createdAt: story.created_at,
        items: story.items,
      }));
    },
    async retryCg(storyId, resourceId) {
      const payload = await invokePayload<{ story: StoryPayload }>(client, rpcMethods["cg.retry"], {
        story_id: storyId,
        resource_id: resourceId,
      });
      return rememberStory(payload.story);
    },
    async regenerateCg(storyId, resourceId) {
      const payload = await invokePayload<{ story: StoryPayload }>(client, rpcMethods["cg.regenerate"], {
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
    voices: mergeVoices(previous.voices, incoming.voices),
  };
}

function voiceKey(voice: Pick<StoryVoice, "beatId" | "fragmentIndex">) {
  return `${voice.beatId}:${voice.fragmentIndex}`;
}

/** Saving a voice does not advance the Story revision, so a later read may still carry the older list. */
function mergeVoices(previous: StoryVoice[], incoming: StoryVoice[]) {
  const voices = new Map(previous.map((voice) => [voiceKey(voice), voice]));
  for (const voice of incoming) voices.set(voiceKey(voice), voice);
  return [...voices.values()];
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
