import type { StoryBeat, StoryCgGallery, StoryDetails, StoryOperation, StorySummary } from "./types";

/** Applies the latest Story status to an existing launcher entry. */
export function replaceStorySummary(stories: StorySummary[], story: StoryDetails) {
  const index = stories.findIndex((candidate) => candidate.storyId === story.id);
  if (index < 0) return stories;
  const current = stories[index];
  const currentTimeBand = story.currentTimeBand;
  const nextScene = story.currentScene;
  const sameScene = current.currentScene.key === nextScene.key
    && current.currentScene.name === nextScene.name
    && current.currentScene.characterIds.length === nextScene.characterIds.length
    && current.currentScene.characterIds.every((id, index) => id === nextScene.characterIds[index]);
  if (current.title === story.title && current.status === story.status && current.currentStoryDate === story.currentStoryDate && current.currentTimeBand === currentTimeBand && sameScene) return stories;
  return stories.map((candidate, candidateIndex) => candidateIndex === index
    ? { ...candidate, title: story.title, status: story.status, currentStoryDate: story.currentStoryDate, currentTimeBand, currentScene: nextScene }
    : candidate);
}

/** Applies the authoritative Story read model returned by a visual-resource retry. */
export function replaceStoryGallery(galleries: StoryCgGallery[], story: StoryDetails) {
  const index = galleries.findIndex((gallery) => gallery.storyId === story.id);
  if (index < 0) return galleries;
  const current = galleries[index];
  const items = story.cgGallery;
  if (
    current.title === story.title
    && current.status === story.status
    && current.items.length === items.length
    && current.items.every((item, itemIndex) => item === items[itemIndex])
  ) return galleries;
  return galleries.map((gallery, galleryIndex) => galleryIndex === index
    ? { ...gallery, title: story.title, status: story.status, items }
    : gallery);
}

/** Returns the latest Story visual that still has a usable local asset path. */
export function selectActiveStoryVisualResource(story: Pick<StoryDetails, "backgroundResource" | "cgGallery" | "currentScene">) {
  const activeSceneKey = story.currentScene.key;
  if (!activeSceneKey) return null;
  return [...story.cgGallery].reverse().find((resource) => resource.sceneKey === activeSceneKey && resource.path)
    ?? (story.backgroundResource?.sceneKey === activeSceneKey && story.backgroundResource.path
      ? story.backgroundResource
      : null);
}

/** Returns whether the frozen Story role is a participant in the current scene. */
export function isStoryRoleInCurrentScene(story: Pick<StoryDetails, "currentScene" | "roleSnapshot">) {
  const roleId = story.roleSnapshot.id?.trim() ?? "";
  return Boolean(roleId && story.currentScene.characterIds.includes(roleId));
}

/** Returns whether Story creation stopped on a failed opening Turn. */
export function isStoryOpeningFailed(story: Pick<StoryDetails, "turns">) {
  return story.turns.some((turn) => turn.kind === "opening" && turn.status === "failed");
}

/** Converts a persisted Story resource error code into stable player-facing copy. */
export function getStoryResourceErrorMessage(errorCode: string | null) {
  const messages: Record<string, string> = {
    provider_not_configured: "图片生成工具未配置",
    invalid_image_request: "图片请求无效",
    resource_generation_failed: "图片生成失败",
    generation_interrupted: "上次图片生成被中断",
    generation_cancelled: "图片生成已取消",
    generation_timeout: "图片生成超时",
  };
  return (errorCode && messages[errorCode]) || (errorCode ? `图片生成失败（${errorCode}）` : "图片生成失败");
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

/** Returns whether the game surface should render the player input field. */
export function canShowStoryInput(story: StoryDetails | null, busy: boolean, hasUnpresentedBeats: boolean) {
  return !busy && !hasUnpresentedBeats && canSubmitStoryInput(story);
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
