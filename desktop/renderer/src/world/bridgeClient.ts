import type {
  NativeIdentityDraft,
  SceneBeat,
  WorldCreationDraft,
  WorldCreationInput,
  WorldDetails,
  WorldSummary,
} from "./types";
import { WorldBridgeError } from "./types";

type DesktopInvoke = typeof window.miraDesktop.invoke;

type StorySummaryPayload = {
  story_id: string;
  title: string;
  status: string;
  created_at: string;
};

type StoryBeatPayload = {
  id: string;
  sequence: number;
  effective_at: string;
  text: string;
  kind: "dialogue" | "action" | "narration";
  speaker?: string | null;
};

type StoryPayload = {
  id: string;
  title: string;
  background: string;
  status: string;
  revision: number;
  roleSnapshot: { id?: string; name?: string; avatar?: string | null };
  playerProfile: { display_name?: string; appearance?: string; identity?: string };
  segment: { startsAt: string; operation: string };
  beats: StoryBeatPayload[];
};

async function invokePayload<T>(invoke: DesktopInvoke, method: string, payload: Record<string, unknown>) {
  const response = await invoke({ method, payload });
  if (response.error) throw new WorldBridgeError(response.error.message, response.error.code);
  return response.payload as T;
}

function toWorldSummary(story: StorySummaryPayload): WorldSummary {
  return {
    id: story.story_id,
    name: story.title,
    premise: "",
    currentTimeLabel: story.created_at,
    currentDayIndex: 1,
    activeOcId: "player",
    status: story.status === "archived" ? "stopped" : "action_required",
  };
}

function toSceneBeat(beat: StoryBeatPayload): SceneBeat {
  return {
    id: beat.id,
    order: beat.sequence,
    dayIndex: 1,
    timeLabel: beat.effective_at,
    speakerName: beat.speaker ?? undefined,
    kind: beat.kind === "narration" ? "environment" : beat.kind,
    content: beat.text,
    presentationMode: "narrative",
  };
}

function toWorldDetails(story: StoryPayload): WorldDetails {
  const beats = story.beats.map(toSceneBeat);
  const playerName = story.playerProfile.display_name?.trim() || "玩家";
  const roleName = story.roleSnapshot.name?.trim() || "角色";
  const status = story.segment.operation === "generating" ? "running" : "action_required";
  return {
    id: story.id,
    name: story.title,
    premise: story.background,
    currentTimeLabel: story.segment.startsAt,
    currentDayIndex: 1,
    activeOcId: "player",
    status,
    days: [{ dayIndex: 1, title: "剧情", status: "current", events: beats }],
    ocs: [{
      id: "player",
      name: playerName,
      identity: story.playerProfile.identity?.trim() || "",
      location: story.playerProfile.appearance?.trim() || "",
      primaryGoal: "推进剧情",
      constraints: [],
      autonomy: "manual",
      isActive: true,
    }],
    scene: {
      title: story.title,
      location: "",
      timeLabel: story.segment.startsAt,
      participants: [{ id: "player", name: playerName, role: "controlled_oc" }, { id: story.roleSnapshot.id || "role", name: roleName, role: "actor" }],
      beats,
      actionPrompt: story.segment.operation === "generating" ? "剧情正在生成..." : "写下你的行动或回应...",
      opportunities: [],
      barriers: [],
    },
    relatedCharacters: [{ id: story.roleSnapshot.id || "role", name: roleName, relationship: "故事角色" }],
    performance: { active: false, label: "", canCancel: false },
  };
}

function startsAtChina(entryTime: string): string {
  if (/([+-]\d{2}:\d{2}|Z)$/i.test(entryTime)) return entryTime;
  return `${entryTime}:00+08:00`;
}

/** Adapter that keeps the existing workspace UI on top of the Story bridge contract. */
export interface WorldBridgeClient {
  listWorlds(): Promise<WorldSummary[]>;
  getWorld(worldId: string): Promise<WorldDetails>;
  previewDraft(input: WorldCreationInput): Promise<WorldCreationDraft>;
  confirmDraft(draftId: string, identities: NativeIdentityDraft[]): Promise<WorldDetails>;
  completeDay(worldId: string, content: string): Promise<void>;
  advance(worldId: string): Promise<void>;
}

/** Creates the Story-backed client used by the retained desktop workspace. */
export function createWorldBridgeClient(invoke: DesktopInvoke = window.miraDesktop.invoke): WorldBridgeClient {
  const revisions = new Map<string, number>();
  const drafts = new Map<string, WorldCreationInput>();

  async function getStory(worldId: string) {
    const story = (await invokePayload<{ story: StoryPayload }>(invoke, "stories.get", { story_id: worldId })).story;
    revisions.set(story.id, story.revision);
    return toWorldDetails(story);
  }

  return {
    async listWorlds() {
      const payload = await invokePayload<{ stories: StorySummaryPayload[] }>(invoke, "stories.list", {});
      return payload.stories.map(toWorldSummary);
    },
    getWorld: getStory,
    async previewDraft(input) {
      if (input.selectedRoleIds.length !== 1) throw new WorldBridgeError("请选择一位角色", "role_required");
      const id = globalThis.crypto?.randomUUID?.() ?? `story-draft-${Date.now().toString(36)}`;
      drafts.set(id, input);
      return {
        id,
        input,
        nativeIdentities: [{
          roleId: input.selectedRoleIds[0],
          roleName: "选定角色",
          nativeName: "",
          identity: "",
          history: "",
          relationships: "",
          accepted: true,
        }],
      };
    },
    async confirmDraft(draftId) {
      const draft = drafts.get(draftId);
      if (!draft) throw new WorldBridgeError("创建草案已失效，请重新填写", "draft_not_found");
      const payload = await invokePayload<{ story: StoryPayload }>(invoke, "stories.create", {
        title: draft.name,
        background: draft.premise,
        starts_at: startsAtChina(draft.firstOc.entryTime),
        role_id: draft.selectedRoleIds[0],
        player_profile: {
          display_name: draft.firstOc.name,
          appearance: draft.firstOc.entryLocation,
          identity: draft.firstOc.identity,
        },
      });
      drafts.delete(draftId);
      revisions.set(payload.story.id, payload.story.revision);
      return toWorldDetails(payload.story);
    },
    async completeDay(worldId, content) {
      const payload = await invokePayload<{ story: StoryPayload }>(invoke, "stories.input", {
        story_id: worldId,
        input: content,
        expected_revision: revisions.get(worldId) ?? 0,
      });
      revisions.set(payload.story.id, payload.story.revision);
    },
    async advance(worldId) {
      const payload = await invokePayload<{ story: StoryPayload }>(invoke, "stories.continue", {
        story_id: worldId,
        expected_revision: revisions.get(worldId) ?? 0,
      });
      revisions.set(payload.story.id, payload.story.revision);
    },
  };
}
