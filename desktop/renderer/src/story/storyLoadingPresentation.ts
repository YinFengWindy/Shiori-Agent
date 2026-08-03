export type StoryLoadingPresentation =
  | { kind: "hidden" }
  | { kind: "transition" }
  | { kind: "progress"; loaded: number; total: number; ratio: number };

type StoryLoadingInput = {
  elapsedMs: number;
  loaded: number;
  total: number;
};

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
