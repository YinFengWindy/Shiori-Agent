/** Visual state for the loading surface before the next Story route is mounted. */
export type StoryLoadingPresentation =
  | { kind: "hidden" }
  | { kind: "transition" }
  | { kind: "progress"; loaded: number; total: number; ratio: number };

/** Loading copy and progress semantics for the Story launcher and gameplay entry. */
export type StoryLoadingMode = "listing" | "story";

/** Real loading phases reported by the Story list and gameplay workflows. */
export type StoryListingLoadingPhase = "reading-list" | "preparing-menu" | "menu-ready";

/** Real loading phases reported while restoring one Story for gameplay. */
export type StoryGameplayLoadingPhase = "reading-story" | "restoring-progress" | "preparing-opening" | "opening-ready";

/** Union of loading phases accepted by the Story loading surface. */
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
    stageLabel: "Story menu loading stages",
    stages: ["Read story list", "Prepare menu"],
    progressLabel: "Read story list",
    railLabel: "Story menu loading",
  },
  story: {
    stageLabel: "Story loading stages",
    stages: ["Read story", "Restore progress", "Prepare opening"],
    progressLabel: "Prepare assets",
    railLabel: "Story loading",
  },
};

const storyLoadingPhaseCopy: Record<StoryLoadingPhase, Pick<StoryLoadingCopy, "heading" | "currentStage" | "activeStage">> = {
  "reading-list": { heading: "Preparing", currentStage: "Read story list", activeStage: 0 },
  "preparing-menu": { heading: "Preparing", currentStage: "Prepare menu", activeStage: 1 },
  "menu-ready": { heading: "Preparing", currentStage: "Story menu ready", activeStage: 2 },
  "reading-story": { heading: "Preparing", currentStage: "Read story", activeStage: 0 },
  "restoring-progress": { heading: "Preparing", currentStage: "Restore progress", activeStage: 1 },
  "preparing-opening": { heading: "Preparing", currentStage: "Prepare opening", activeStage: 2 },
  "opening-ready": { heading: "Preparing", currentStage: "Opening ready", activeStage: 3 },
};

/** Returns the copy contract for one Story loading route. */
export function resolveStoryLoadingCopy(mode: StoryLoadingMode, phase: StoryLoadingPhase): StoryLoadingCopy {
  const phaseKey: StoryLoadingPhase = mode === "listing"
    ? phase === "preparing-menu" || phase === "menu-ready" ? phase : "reading-list"
    : phase === "restoring-progress" || phase === "preparing-opening" || phase === "opening-ready" ? phase : "reading-story";
  return { ...storyLoadingCopy[mode], ...storyLoadingPhaseCopy[phaseKey] };
}

type StoryLoadingInput = {
  elapsedMs: number;
  loaded: number;
  total: number;
};

/** Minimum time each real Story loading stage remains active before it completes. */
export const storyLoadingStageMinMs = 900;
/** Keeps the all-complete state visible before the next Story surface replaces it. */
export const storyLoadingCompletionHoldMs = 420;

/** Waits for the remaining stage duration without delaying slow bridge operations. */
export async function waitForMinimumStoryLoadingStage(
  startedAt: number,
  now = Date.now(),
  sleep = (delayMs: number) => new Promise<void>((resolve) => window.setTimeout(resolve, delayMs)),
) {
  const elapsedMs = Math.max(0, now - startedAt);
  const remainingMs = storyLoadingStageMinMs - elapsedMs;
  if (remainingMs <= 0) return;
  await sleep(remainingMs);
}

/** Holds the all-complete loading state long enough for its checkmarks to register. */
export async function waitForStoryLoadingCompletion(
  sleep = (delayMs: number) => new Promise<void>((resolve) => window.setTimeout(resolve, delayMs)),
) {
  await sleep(storyLoadingCompletionHoldMs);
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
