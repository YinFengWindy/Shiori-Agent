import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { WorldGameControls } from "./WorldGameControls";
import { WorldGameInteraction } from "./WorldGameInteraction";
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
  onSubmitAction: (content: string) => Promise<boolean>;
  onAdvance: () => void;
  onResolveBarrier: (barrier: DecisionBarrier, choiceId: string) => void;
  onRedrawShot: (shotId: string) => void;
  onPause: () => Promise<void> | void;
  onResume: () => Promise<void> | void;
  onCheckpoint: (planId: string, cueIndex: number) => Promise<void> | void;
};

function initialVisual(beat: SceneBeat | null) {
  const shot = beat?.shot;
  if (!shot) return undefined;
  const asset = shot.assets.find((item) => item.id === shot.activeAssetId) ?? shot.assets[0];
  return asset ? { id: `shot-${asset.id}`, url: asset.imageUrl } : undefined;
}

/** Owns the World visual-novel lifecycle while management views remain separate. */
export function WorldGameSurface({ world, runtime, busy = false, onOpenTimeline, onExitWorkspace, onSubmitAction, onAdvance, onResolveBarrier, onRedrawShot, onPause, onResume, onCheckpoint }: WorldGameSurfaceProps) {
  const { plan, preloadPlan, beat, session, startCueIndex, canPlay } = selectWorldGamePresentation(world);
  const [paused, setPaused] = useState(session?.status === "paused");
  const [skipVersion, setSkipVersion] = useState(0);
  const isPaused = paused || session?.status === "paused";
  const performing = canPlay && !isPaused;
  const hydratedPlan = plan ? hydrateWorldPresentationAssets(plan) : null;
  const hydratedPreloadPlan = preloadPlan ? hydrateWorldPresentationAssets(preloadPlan) : undefined;
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
      {hydratedPlan ? <WorldStage plan={hydratedPlan} preloadPlan={hydratedPreloadPlan} fallbackText={beat?.content ?? ""} runtime={runtime} initialVisual={initialVisual(beat)} startCueIndex={startCueIndex} paused={isPaused} skipVersion={skipVersion} onCueComplete={(cue) => onCheckpoint(cue.planId, cue.sequence)} /> : beat?.shot?.assets[0] ? <img className="absolute inset-0 h-full w-full object-cover" src={beat.shot.assets[0].imageUrl} alt={beat.shot.prompt} /> : <div className="absolute inset-0 bg-[#252C28]" />}
      <div className="pointer-events-none absolute inset-0 bg-black/35" />
      <WorldGameControls paused={isPaused} onPause={pause} onResume={resume} onSkip={() => setSkipVersion((value) => value + 1)} onRedraw={beat?.shot ? () => onRedrawShot(beat.shot!.id) : undefined} onOpenTimeline={onOpenTimeline} onExitWorkspace={exitWorkspace} />
      <WorldGameInteraction world={world} beat={beat} paused={isPaused} performing={performing} busy={busy} dialogue={dialogue} onContinueDialogue={() => { runtime.continueDialogue(); }} onSubmitAction={onSubmitAction} onAdvance={onAdvance} onResolveBarrier={onResolveBarrier} />
    </section>
  );
}
