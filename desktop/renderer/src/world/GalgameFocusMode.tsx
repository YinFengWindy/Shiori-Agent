import { ArrowClockwise, ArrowLeft, Pause, Play, SkipForward, X } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";
import type { PerformancePlan } from "./presentationProtocol";
import type { SceneBeat } from "./types";
import { hydrateWorldPresentationAssets } from "./worldPresentationAssets";
import { WorldStage } from "./WorldStage";

type GalgameFocusModeProps = {
  worldName: string;
  beat: SceneBeat;
  plan?: PerformancePlan;
  preloadPlan?: PerformancePlan;
  startCueIndex?: number;
  paused?: boolean;
  onExit: () => void;
  onRedrawShot: (shotId: string) => void;
  onPause?: () => Promise<void> | void;
  onResume?: () => Promise<void> | void;
  onCheckpoint?: (planId: string, cueIndex: number) => Promise<void> | void;
};

function fallbackPlan(beat: SceneBeat): PerformancePlan {
  const planId = `fallback-${beat.id}`;
  return {
    schemaVersion: 1,
    planId,
    worldId: "fallback",
    eventId: beat.id,
    sourceSequence: beat.order,
    cues: [{
      schemaVersion: 1,
      cueId: `${planId}-text`,
      planId,
      sequence: 0,
      kind: "text",
      payload: { text: beat.content },
      parallelGroup: null,
      blocking: true,
      completionState: "completed",
      skipState: "skipped",
      checkpoint: true,
    }],
  };
}

/** Owns React presentation controls without coupling the stage to world simulation. */
export function GalgameFocusMode({ worldName, beat, plan, preloadPlan, startCueIndex = 0, paused = false, onExit, onRedrawShot, onPause, onResume, onCheckpoint }: GalgameFocusModeProps) {
  const [locallyPaused, setLocallyPaused] = useState(paused);
  const [skipVersion, setSkipVersion] = useState(0);
  const activePlan = useMemo(
    () => hydrateWorldPresentationAssets(plan ?? beat.performancePlan ?? fallbackPlan(beat)),
    [beat, plan],
  );
  const hydratedPreloadPlan = useMemo(
    () => preloadPlan ? hydrateWorldPresentationAssets(preloadPlan) : undefined,
    [preloadPlan],
  );
  const initialShot = useMemo(() => {
    const shot = beat.shot;
    if (!shot) return undefined;
    const asset = shot.assets.find((item) => item.id === shot.activeAssetId) ?? shot.assets[0];
    return asset ? { id: `shot-${asset.id}`, url: asset.imageUrl } : undefined;
  }, [beat.shot]);

  useEffect(() => setLocallyPaused(paused), [paused]);

  return (
    <section className="fixed inset-0 z-[100] overflow-hidden bg-[#171A18] text-white" data-testid="galgame-focus-mode">
      <WorldStage
        plan={activePlan}
        preloadPlan={hydratedPreloadPlan}
        fallbackText={beat.content}
        initialVisual={initialShot}
        startCueIndex={startCueIndex}
        paused={locallyPaused}
        skipVersion={skipVersion}
        onCueComplete={(cue) => onCheckpoint?.(activePlan.planId, cue.sequence)}
      />
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/90 via-transparent to-black/35" />
      <header className="absolute inset-x-0 top-0 z-10 flex items-center justify-between p-5">
        <span className="font-serif text-sm tracking-normal text-white/75">{worldName}</span>
        <div className="flex items-center gap-2">
          {beat.shot ? <button className="pointer-events-auto grid h-10 w-10 place-items-center rounded-md bg-black/35 text-white backdrop-blur-sm hover:bg-black/55" type="button" aria-label="重绘镜头" title="重绘镜头" onClick={() => onRedrawShot(beat.shot!.id)}><ArrowClockwise /></button> : null}
          <button className="pointer-events-auto grid h-10 w-10 place-items-center rounded-md bg-black/35 text-white backdrop-blur-sm hover:bg-black/55" type="button" aria-label={locallyPaused ? "继续演出" : "暂停演出"} title={locallyPaused ? "继续演出" : "暂停演出"} onClick={() => {
            const nextPaused = !locallyPaused;
            setLocallyPaused(nextPaused);
            if (nextPaused) void onPause?.();
            else void onResume?.();
          }}>{locallyPaused ? <Play /> : <Pause />}</button>
          <button className="pointer-events-auto grid h-10 w-10 place-items-center rounded-md bg-black/35 text-white backdrop-blur-sm hover:bg-black/55" type="button" aria-label="跳过当前演出" title="跳过当前演出" onClick={() => setSkipVersion((value) => value + 1)}><SkipForward /></button>
          <button className="pointer-events-auto grid h-10 w-10 place-items-center rounded-md bg-black/35 text-white backdrop-blur-sm hover:bg-black/55" type="button" aria-label="退出焦点模式" title="退出焦点模式" onClick={onExit}><X /></button>
        </div>
      </header>
      <div className="absolute inset-x-0 bottom-0 z-10 px-[clamp(24px,8vw,120px)] pb-[clamp(28px,7vh,72px)]"><div className="max-w-4xl border-l-2 border-[#E59A70] bg-black/45 px-6 py-5 backdrop-blur-md">{beat.speakerName ? <h1 className="m-0 mb-2 font-serif text-lg font-semibold text-[#F3B18B]">{beat.speakerName}</h1> : null}<p className="m-0 whitespace-pre-wrap font-serif text-lg leading-8 text-white">{beat.content}</p></div><button className="pointer-events-auto mt-3 inline-flex h-9 items-center gap-2 rounded-md bg-black/35 px-3 text-xs text-white/80 hover:bg-black/55" type="button" onClick={onExit}><ArrowLeft />返回工作台</button></div>
    </section>
  );
}
