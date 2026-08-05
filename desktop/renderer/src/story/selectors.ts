import type { StoryBeat, StoryCgGallery, StoryDetails, StoryOperation, StorySummary } from "./types";

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
export function selectActiveStoryVisualResource(story: Pick<StoryDetails, "backgroundResource" | "cgGallery">) {
  return [...story.cgGallery].reverse().find((resource) => resource.kind === "cg" && resource.path)
    ?? (story.backgroundResource?.path ? story.backgroundResource : null);
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
