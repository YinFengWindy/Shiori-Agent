import { useCallback, useEffect, useMemo, useState } from "react";
import type { WorldBridgeClient } from "./bridgeClient";
import { WorldGameControls } from "./WorldGameControls";
import { WorldGameInteraction } from "./WorldGameInteraction";
import type { DecisionBarrier, SceneBeat, WorldDetails } from "./types";
import { hydrateWorldPresentationAssets } from "./worldPresentationAssets";
import { WorldStage } from "./WorldStage";
import { selectWorldGamePresentation } from "./worldGamePresentation";

type WorldGameSurfaceProps = {
  world: WorldDetails;
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
  synthesizeVoice: WorldBridgeClient["synthesizeVoice"];
};

function initialVisual(beat: SceneBeat | null) {
  const shot = beat?.shot;
  if (!shot) return undefined;
  const asset = shot.assets.find((item) => item.id === shot.activeAssetId) ?? shot.assets[0];
  return asset ? { id: `shot-${asset.id}`, url: asset.imageUrl } : undefined;
}

/** Owns the World visual-novel lifecycle while management views remain separate. */
export function WorldGameSurface({ world, busy = false, onOpenTimeline, onExitWorkspace, onSubmitAction, onAdvance, onResolveBarrier, onRedrawShot, onPause, onResume, onCheckpoint, synthesizeVoice }: WorldGameSurfaceProps) {
  const { plan, preloadPlan, beat, session, startCueIndex, canPlay } = selectWorldGamePresentation(world);
  const [paused, setPaused] = useState(session?.status === "paused");
  const [skipVersion, setSkipVersion] = useState(0);
  const isPaused = paused || session?.status === "paused";
  const performing = canPlay && !isPaused;
  const hydratedPlan = useMemo(() => plan ? hydrateWorldPresentationAssets(plan) : null, [plan]);
  const hydratedPreloadPlan = useMemo(() => preloadPlan ? hydrateWorldPresentationAssets(preloadPlan) : undefined, [preloadPlan]);

  useEffect(() => {
    setPaused(session?.status === "paused");
  }, [session?.status]);

  const pause = useCallback(() => {
    if (!canPlay || isPaused) return;
    setPaused(true);
    void onPause();
  }, [canPlay, isPaused, onPause]);
  const resume = useCallback(() => {
    if (!canPlay || !isPaused) return;
    setPaused(false);
    void onResume();
  }, [canPlay, isPaused, onResume]);
  const exitWorkspace = useCallback(() => {
    if (canPlay && !isPaused) pause();
    onExitWorkspace();
  }, [canPlay, isPaused, onExitWorkspace, pause]);

  return (
    <section className="relative h-full min-h-0 overflow-hidden bg-[#151816] text-white" data-testid="world-game-surface">
      {hydratedPlan ? <WorldStage plan={hydratedPlan} preloadPlan={hydratedPreloadPlan} fallbackText={beat?.content ?? ""} initialVisual={initialVisual(beat)} startCueIndex={startCueIndex} paused={isPaused} skipVersion={skipVersion} synthesizeVoice={synthesizeVoice} onCueComplete={(cue) => onCheckpoint(cue.planId, cue.sequence)} /> : beat?.shot?.assets[0] ? <img className="absolute inset-0 h-full w-full object-cover" src={beat.shot.assets[0].imageUrl} alt={beat.shot.prompt} /> : <div className="absolute inset-0 bg-[#252C28]" />}
      <div className="pointer-events-none absolute inset-0 bg-black/35" />
      <WorldGameControls worldName={world.name} paused={isPaused} onPause={pause} onResume={resume} onSkip={() => setSkipVersion((value) => value + 1)} onRedraw={beat?.shot ? () => onRedrawShot(beat.shot!.id) : undefined} onOpenTimeline={onOpenTimeline} onExitWorkspace={exitWorkspace} />
      <WorldGameInteraction world={world} beat={beat} paused={isPaused} performing={performing} busy={busy} onSubmitAction={onSubmitAction} onAdvance={onAdvance} onResolveBarrier={onResolveBarrier} />
    </section>
  );
}
