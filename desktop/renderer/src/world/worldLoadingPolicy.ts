export type WorldLoadingPresentation =
  | { kind: "hidden" }
  | { kind: "transition" }
  | { kind: "progress"; loaded: number; total: number; ratio: number };

type WorldLoadingPolicyInput = {
  elapsedMs: number;
  loaded: number;
  total: number;
};

/** Maps elapsed time and measurable work to the three required loading treatments. */
export function resolveWorldLoadingPresentation(input: WorldLoadingPolicyInput): WorldLoadingPresentation {
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
