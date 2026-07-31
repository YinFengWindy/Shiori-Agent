import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { WorldGameControls } from "./WorldGameControls";
import { WorldGameInteraction } from "./WorldGameInteraction";
import type { PerformancePlan } from "./presentationProtocol";
import type { DecisionBarrier, SceneBeat, WorldDetails } from "./types";
import { hydrateWorldPresentationAssets } from "./worldPresentationAssets";
import { WorldStage } from "./WorldStage";
import { selectWorldGamePresentation } from "./worldGamePresentation";
import type { WorldPresentationRuntime } from "./worldPresentationRuntime";

type WorldGameSurfaceProps = {
  world: WorldDetails;
  runtime: WorldPresentationRuntime;
  busy?: boolean;
  onOpenTimeline: () => void;
  onExitWorkspace: () => void;
  onSceneComplete: () => void;
  onResolveBarrier: (barrier: DecisionBarrier, choiceId: string) => void;
  onRedrawShot: (shotId: string) => void;
  onPause: () => Promise<void> | void;
  onResume: () => Promise<void> | void;
  onCheckpoint: (planId: string, cueIndex: number) => Promise<boolean> | boolean;
};

function initialVisual(beat: SceneBeat | null) {
  const shot = beat?.shot;
  if (!shot) return undefined;
  const asset = shot.assets.find((item) => item.id === shot.activeAssetId) ?? shot.assets[0];
  return asset ? { id: `shot-${asset.id}`, url: asset.imageUrl } : undefined;
}

function createWorldPlanHydrator() {
  const cache = new Map<string, PerformancePlan>();
  return (plan: PerformancePlan | null | undefined) => {
    if (!plan) return null;
    const cached = cache.get(plan.planId);
    if (cached) return cached;
    const hydrated = hydrateWorldPresentationAssets(plan);
    cache.set(plan.planId, hydrated);
    if (cache.size > 4) cache.delete(cache.keys().next().value!);
    return hydrated;
  };
}

/** Hydrates immutable scene plans while preserving playback identity across bridge refreshes. */
export function useHydratedWorldPlans(plan: PerformancePlan | null, preloadPlan?: PerformancePlan) {
  const [hydratePlan] = useState(createWorldPlanHydrator);
  const hydratedPlan = hydratePlan(plan);
  const hydratedPreloadPlan = hydratePlan(preloadPlan);

  return {
    plan: hydratedPlan,
    preloadPlan: hydratedPreloadPlan ?? undefined,
  };
}

/** Owns the World visual-novel lifecycle while management views remain separate. */
export function WorldGameSurface({ world, runtime, busy = false, onOpenTimeline, onExitWorkspace, onSceneComplete, onResolveBarrier, onRedrawShot, onPause, onResume, onCheckpoint }: WorldGameSurfaceProps) {
  const { plan, preloadPlan, beat, session, startCueIndex, canPlay } = selectWorldGamePresentation(world);
  const [paused, setPaused] = useState(session?.status === "paused");
  const [skipVersion, setSkipVersion] = useState(0);
  const isPaused = paused || session?.status === "paused";
  const performing = canPlay && !isPaused;
  const { plan: hydratedPlan, preloadPlan: hydratedPreloadPlan } = useHydratedWorldPlans(plan, preloadPlan);
  const subscribeDialogue = useCallback((listener: () => void) => runtime.subscribeDialogue(listener), [runtime]);
  const readDialogue = useCallback(() => runtime.dialogueSnapshot(), [runtime]);
  const dialogue = useSyncExternalStore(subscribeDialogue, readDialogue, readDialogue);

  useEffect(() => {
    setPaused(session?.status === "paused");
  }, [session?.status]);

  function pause() {
    if (!canPlay || isPaused) return;
    setPaused(true);
    void onPause();
  }
  function resume() {
    if (!canPlay || !isPaused) return;
    setPaused(false);
    void onResume();
  }
  function exitWorkspace() {
    if (canPlay && !isPaused) pause();
    onExitWorkspace();
  }

  return (
    <section className="relative h-full min-h-0 overflow-hidden bg-[#151816] text-white" data-testid="world-game-surface">
      {hydratedPlan ? <WorldStage plan={hydratedPlan} preloadPlan={hydratedPreloadPlan} fallbackText={beat?.content ?? ""} runtime={runtime} initialVisual={initialVisual(beat)} startCueIndex={startCueIndex} paused={isPaused} skipVersion={skipVersion} onCueComplete={async (cue) => { if (await onCheckpoint(cue.planId, cue.sequence)) onSceneComplete(); }} /> : beat?.shot?.assets[0] ? <img className="absolute inset-0 h-full w-full object-cover" src={beat.shot.assets[0].imageUrl} alt={beat.shot.prompt} /> : <div className="absolute inset-0 bg-[#252C28]" />}
      <div className="pointer-events-none absolute inset-0 bg-black/35" />
      <WorldGameControls paused={isPaused} onPause={pause} onResume={resume} onSkip={() => setSkipVersion((value) => value + 1)} onRedraw={beat?.shot ? () => onRedrawShot(beat.shot!.id) : undefined} onOpenTimeline={onOpenTimeline} onExitWorkspace={exitWorkspace} />
      <WorldGameInteraction world={world} beat={beat} paused={isPaused} performing={performing} busy={busy} dialogue={dialogue} allowFreeAction={false} onContinueDialogue={() => { runtime.continueDialogue(); }} onSubmitAction={async () => false} onAdvance={() => undefined} onResolveBarrier={onResolveBarrier} />
    </section>
  );
}
