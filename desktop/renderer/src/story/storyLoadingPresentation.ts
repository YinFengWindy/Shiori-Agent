export type StoryLoadingPresentation =
  | { kind: "hidden" }
  | { kind: "transition" }
  | { kind: "progress"; loaded: number; total: number; ratio: number };

/** Loading copy and progress semantics for the Story launcher and gameplay entry. */
export type StoryLoadingMode = "listing" | "story";

/** Real loading phases reported by the Story list and gameplay workflows. */
export type StoryListingLoadingPhase = "reading-list" | "preparing-menu";
export type StoryGameplayLoadingPhase = "reading-story" | "restoring-progress" | "preparing-opening";
export type StoryLoadingPhase = StoryListingLoadingPhase | StoryGameplayLoadingPhase;

/** Copy, accessibility labels, and progress semantics for one loading route. */
export type StoryLoadingCopy = {
  heading: string;
  currentStage: string;
  stageLabel: string;
  stages: readonly string[];
  progressLabel: string;
  railLabel: string;
  activeStage: number;
};

const storyLoadingCopy: Record<StoryLoadingMode, Omit<StoryLoadingCopy, "heading" | "currentStage" | "activeStage">> = {
    listing: {
    stageLabel: "主菜单加载阶段",
    stages: ["读取故事列表", "准备菜单", "完成"],
    progressLabel: "读取故事列表",
    railLabel: "故事主菜单加载",
  },
  story: {
    stageLabel: "剧情加载阶段",
    stages: ["读取剧情", "恢复进度", "准备开场"],
    progressLabel: "准备素材",
    railLabel: "剧情加载",
  },
};

const storyLoadingPhaseCopy: Record<StoryLoadingPhase, Pick<StoryLoadingCopy, "heading" | "currentStage" | "activeStage">> = {
  "reading-list": { heading: "准备故事主菜单", currentStage: "读取故事列表", activeStage: 0 },
  "preparing-menu": { heading: "准备故事主菜单", currentStage: "准备菜单", activeStage: 1 },
  "reading-story": { heading: "进入剧情", currentStage: "读取剧情", activeStage: 0 },
  "restoring-progress": { heading: "进入剧情", currentStage: "恢复进度", activeStage: 1 },
  "preparing-opening": { heading: "进入剧情", currentStage: "准备开场", activeStage: 2 },
};

/** Returns the copy contract for one Story loading route. */
export function resolveStoryLoadingCopy(mode: StoryLoadingMode, phase: StoryLoadingPhase): StoryLoadingCopy {
  const phaseKey: StoryLoadingPhase = mode === "listing"
    ? phase === "preparing-menu" ? phase : "reading-list"
    : phase === "restoring-progress" || phase === "preparing-opening" ? phase : "reading-story";
  return { ...storyLoadingCopy[mode], ...storyLoadingPhaseCopy[phaseKey] };
}

type StoryLoadingInput = {
  elapsedMs: number;
  loaded: number;
  total: number;
};

/** Minimum time a successful Story entry spends in the loading transition. */
export const minStoryLoadingMs = 2_200;

/** Waits for the remaining minimum loading duration without delaying slow loads. */
export async function waitForMinimumStoryLoading(
  startedAt: number,
  now = Date.now(),
  sleep = (delayMs: number) => new Promise<void>((resolve) => window.setTimeout(resolve, delayMs)),
) {
  const elapsedMs = Math.max(0, now - startedAt);
  const remainingMs = minStoryLoadingMs - elapsedMs;
  if (remainingMs <= 0) return;
  await sleep(remainingMs);
}

/** Maps elapsed time and measurable work to the three required loading treatments. */
export function resolveStoryLoadingPresentation(input: StoryLoadingInput): StoryLoadingPresentation {
  if (input.elapsedMs < 250) return { kind: "hidden" };
  if (input.elapsedMs < 2_000) return { kind: "transition" };
  const total = Math.max(0, input.total);
  const loaded = Math.min(total, Math.max(0, input.loaded));
  return {
    kind: "progress",
    loaded,
    total,
    ratio: total > 0 ? loaded / total : 0,
  };
}
