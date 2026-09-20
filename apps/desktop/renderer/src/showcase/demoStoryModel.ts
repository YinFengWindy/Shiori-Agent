import type { StoryDetails, StoryResource } from "../../../../../plugins/story/ui/types";
import { normalizeStoryTimeBand, STORY_TIME_BANDS } from "../../../../../plugins/story/ui/storyTime";
import { demoRole } from "./demoContent";
import { storyArtwork } from "./demoAssets";
import { storyChapters } from "./demoStoryChapters";

/** Build a genuine Story read model from a public sample or the existing creation form. */
export function createDemoStory(payload: Record<string, unknown> = {}): StoryDetails {
  const id = typeof payload.creation_id === "string" ? `demo-${payload.creation_id}` : "demo-bookshop";
  const date = String(payload.story_date || "2026-09-20");
  const timeBand = normalizeStoryTimeBand(String(payload.time_band || "下午"));
  if (timeBand === "时间未知") throw new Error("请选择有效的故事时段。");
  const profile = payload.player_profile;
  if (profile !== undefined && (!profile || typeof profile !== "object" || !("display_name" in profile) || !("appearance" in profile) || !("identity" in profile))) throw new Error("请填写完整的玩家资料。");
  const story: StoryDetails = {
    id, title: String(payload.title || "雨停之前"), background: String(payload.background || "一场突如其来的雨，把你带进了街角的旧书店。"),
    status: "active", revision: 0,
    roleSnapshot: { id: demoRole.id, name: demoRole.name, description: demoRole.description, avatar: demoRole.avatar_abs, illustrations: [] },
    playerProfile: profile ? { display_name: String(profile.display_name), appearance: String(profile.appearance), identity: String(profile.identity) } : { display_name: "旅人", appearance: "深色外套，肩上沾着细雨。", identity: "偶然路过书店的旅人。" },
    segment: { id: `${id}-segment`, sequence: 1, storyDate: date, timeBand, status: "active", mode: "plot", operation: "idle", openingContext: {}, runtimeSnapshot: {} },
    beats: [], turns: [], cues: [], currentScene: { key: "bookshop", name: "街角旧书店", characterIds: [demoRole.id, "player"] },
    backgroundResource: null, cgGallery: [], currentStoryDate: date, currentTimeBand: timeBand,
  };
  return appendDemoStoryTurn(story, "", "opening");
}

/** Append a prewritten page with the same turns, beats, revision and operation states as Story. */
export function appendDemoStoryTurn(story: StoryDetails, input: string, kind: "opening" | "player" | "continue"): StoryDetails {
  const pageIndex = story.turns.length;
  const chapter = storyChapters[pageIndex];
  if (!chapter) throw new Error("这一段故事已读完。可返回剧情记录重读，或回主菜单新建故事。");
  const currentScene = { ...chapter.scene, characterIds: [demoRole.id, "player"] };
  // A visitor may choose a later opening time; the fixed narrative never moves it back.
  const timeBand = chapter.timeBand && STORY_TIME_BANDS.indexOf(chapter.timeBand) > STORY_TIME_BANDS.indexOf(story.currentTimeBand) ? chapter.timeBand : story.currentTimeBand;
  const timestamp = new Date().toISOString();
  const turnId = `${story.id}-turn-${pageIndex + 1}`;
  const beats = chapter.beats.map((sampleBeat, index) => ({
    ...sampleBeat, id: `${turnId}-beat-${index + 1}`, storyId: story.id, segmentId: story.segment.id,
    turnId, sequence: story.beats.length + index + 1, storyDate: story.currentStoryDate,
    timeBand, speaker: sampleBeat.kind === "dialogue" ? demoRole.name : null, recordedAt: timestamp,
  }));
  const resource: StoryResource = {
    id: `${story.id}-visual-${chapter.artwork}`, storyId: story.id, kind: pageIndex === 0 ? "background" : "cg",
    visualType: "character", sceneKey: currentScene.key, status: "ready", path: storyArtwork[chapter.artwork],
    prompt: currentScene.name, sourceTurnId: turnId, sequence: pageIndex + 1, errorCode: null,
    createdAt: timestamp, updatedAt: timestamp,
  };
  return {
    ...story, revision: story.revision + 1,
    segment: { ...story.segment, timeBand, operation: "awaiting_player" },
    currentScene, currentTimeBand: timeBand,
    beats: [...story.beats, ...beats],
    turns: [...story.turns, { id: turnId, kind, input, status: "committed", attemptId: null, committedBeatIds: beats.map((beat) => beat.id), error: null, createdAt: timestamp, updatedAt: timestamp }],
    backgroundResource: story.backgroundResource ?? resource,
    cgGallery: story.cgGallery.some((existing) => existing.path === resource.path) ? story.cgGallery : [...story.cgGallery, resource],
  };
}

/** Translate the stored read model to the actual catalog RPC's wire shape. */
export function demoStorySummary(story: StoryDetails) {
  return {
    story_id: story.id, relative_db_path: "", title: story.title, status: story.status,
    created_at: story.turns[0]?.createdAt ?? "", current_story_date: story.currentStoryDate,
    current_time_band: story.currentTimeBand,
    current_scene: { key: story.currentScene.key, name: story.currentScene.name, character_ids: story.currentScene.characterIds },
  };
}
