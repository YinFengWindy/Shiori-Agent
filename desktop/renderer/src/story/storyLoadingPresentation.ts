export type StoryLoadingPresentation =
  | { kind: "hidden" }
  | { kind: "transition" }
  | { kind: "progress"; loaded: number; total: number; ratio: number };

/** Loading copy and progress semantics for the Story launcher and gameplay entry. */
export type StoryLoadingMode = "listing" | "story";

/** Copy, accessibility labels, and progress semantics for one loading route. */
export type StoryLoadingCopy = {
  eyebrow: string;
  heading: string;
  currentStage: string;
  stageLabel: string;
  stages: readonly string[];
  progressLabel: string;
  railLabel: string;
  activeStage: number;
};

const storyLoadingCopy: Record<StoryLoadingMode, StoryLoadingCopy> = {
  listing: {
    eyebrow: "Story / Menu",
    heading: "准备故事主菜单",
    currentStage: "读取故事列表",
    stageLabel: "主菜单加载阶段",
    stages: ["读取故事列表", "准备菜单", "完成"],
    progressLabel: "读取故事列表",
    railLabel: "故事主菜单加载",
    activeStage: 0,
  },
  story: {
    eyebrow: "Story / Loading",
    heading: "进入剧情",
    currentStage: "恢复进度",
    stageLabel: "剧情加载阶段",
    stages: ["读取剧情", "恢复进度", "准备开场"],
    progressLabel: "准备素材",
    railLabel: "剧情加载",
    activeStage: 1,
  },
};

/** Returns the copy contract for one Story loading route. */
export function resolveStoryLoadingCopy(mode: StoryLoadingMode): StoryLoadingCopy {
  return storyLoadingCopy[mode];
}

type StoryLoadingInput = {
  elapsedMs: number;
  loaded: number;
  total: number;
};

/** Minimum time a successful Story entry spends in the loading transition. */
export const minStoryLoadingMs = 1_500;

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
