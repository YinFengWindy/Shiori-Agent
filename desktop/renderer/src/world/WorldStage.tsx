import { useEffect, useMemo, useRef, useState } from "react";
import { useLatestRef } from "../shared/useLatestRef";
import type { PerformancePlan, PresentationCue } from "./presentationProtocol";
import type { WorldPresentationRuntime } from "./worldPresentationRuntime";
import {
  createWorldAssetManifest,
  playPresentationPlan,
  TextWorldPresentationRenderer,
  type TextPresentationSnapshot,
  type WorldPresentationPrepareRequest,
  type WorldPresentationRenderer,
} from "./worldPresentationRenderer";
import { resolveWorldLoadingPresentation } from "./worldLoadingPolicy";
import { createWorldStagePlaybackCoordinator } from "./worldStagePlaybackCoordinator";

type WorldStageProps = {
  plan: PerformancePlan;
  preloadPlan?: PerformancePlan;
  fallbackText: string;
  runtime: WorldPresentationRuntime;
  initialVisual?: { id: string; url: string };
  startCueIndex?: number;
  paused?: boolean;
  skipVersion?: number;
  onCueComplete?: (cue: PresentationCue) => Promise<void> | void;
  onPrepareProgress?: (loaded: number, total: number) => void;
};

function initialRequest(
  plan: PerformancePlan,
  preloadPlan: PerformancePlan | undefined,
  fallbackText: string,
  initialVisual: WorldStageProps["initialVisual"],
): WorldPresentationPrepareRequest {
  const manifestById = new Map(
    [...createWorldAssetManifest(plan), ...(preloadPlan ? createWorldAssetManifest(preloadPlan) : [])]
      .map((entry) => [entry.id, entry] as const),
  );
  const manifest = [...manifestById.values()];
  if (initialVisual) manifest.push({ id: initialVisual.id, url: initialVisual.url, kind: "background" });
  return { plan, manifest, initialAssetId: initialVisual?.id, fallbackText };
}

/** Thin React host that owns renderer switching while the route runtime owns durable resources. */
export function WorldStage({
  plan,
  preloadPlan,
  fallbackText,
  runtime,
  initialVisual,
  startCueIndex = 0,
  paused = false,
  skipVersion = 0,
  onCueComplete,
  onPrepareProgress,
}: WorldStageProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<WorldPresentationRenderer | null>(null);
  const checkpointRef = useLatestRef(onCueComplete);
  const progressRef = useLatestRef(onPrepareProgress);
  const skipVersionRef = useRef(skipVersion);
  const pausedRef = useLatestRef(paused);
  const [fallback, setFallback] = useState<TextPresentationSnapshot | null>(null);
  const [presentationError, setPresentationError] = useState<string | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [loadingElapsedMs, setLoadingElapsedMs] = useState(0);
  const [assetProgress, setAssetProgress] = useState({ loaded: 0, total: 0 });
  const initialVisualId = initialVisual?.id;
  const initialVisualUrl = initialVisual?.url;
  const request = useMemo(
    () => initialRequest(
      plan,
      preloadPlan,
      fallbackText,
      initialVisualId && initialVisualUrl ? { id: initialVisualId, url: initialVisualUrl } : undefined,
    ),
    [fallbackText, initialVisualId, initialVisualUrl, plan, preloadPlan],
  );

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const controller = new AbortController();
    let active = true;
    let renderer: WorldPresentationRenderer | null = null;
    let coordinator: ReturnType<typeof createWorldStagePlaybackCoordinator> | null = null;
    const startedAt = performance.now();
    const transitionTimer = setTimeout(() => setLoadingElapsedMs(250), 250);
    const progressTimer = setTimeout(() => setLoadingElapsedMs(2_000), 2_000);
    setFallback(null);
    setPresentationError(null);
    setPreparing(true);
    setLoadingElapsedMs(0);
    setAssetProgress({ loaded: 0, total: request.manifest.length });
    const textRenderer = new TextWorldPresentationRenderer((snapshot) => {
      if (active) setFallback(snapshot);
    });
    const settings = runtime.refreshSettings();

    const reportProgress = (loaded: number, total: number) => {
      if (!active) return;
      setAssetProgress({ loaded, total });
      setLoadingElapsedMs(performance.now() - startedAt);
      progressRef.current?.(loaded, total);
      if (total === 0 || loaded >= total) setPreparing(false);
    };
    const reportFailure = (error: unknown) => {
      if (active && !controller.signal.aborted) {
        setPresentationError(error instanceof Error ? error.message : "演出无法继续");
        setPreparing(false);
      }
    };
    const activateTextRenderer = async () => {
      if (!active || renderer?.kind === "text") return;
      renderer?.dispose();
      renderer = textRenderer;
      rendererRef.current = renderer;
      await renderer.initialize(host);
    };

    void (async () => {
      try {
        const module = await import("./pixiWorldPresentationRenderer");
        if (!active) return;
        const assets = runtime.retainStageResource(
          "pixi-world-assets-v1",
          module.createPixiWorldAssetManager,
          (manager) => manager.dispose(),
        );
        renderer = module.createPixiWorldPresentationRenderer({
          assets,
          onContextLoss: () => {
            const fallbackPromise = coordinator?.activateTextFallback();
            if (fallbackPromise) void fallbackPromise.catch(reportFailure);
          },
          reducedMotion: settings.reducedMotion || settings.motionIntensity === "reduced",
          motionIntensity: settings.motionIntensity,
        });
        rendererRef.current = renderer;
        coordinator = createWorldStagePlaybackCoordinator({
          request,
          startCueIndex,
          signal: controller.signal,
          pixiRenderer: renderer,
          textRenderer,
          onCueComplete: (cue) => active ? checkpointRef.current?.(cue) : undefined,
          onPrepareProgress: reportProgress,
          onCueRendered: (cue) => runtime.handleRenderedCue(cue, request.plan.worldId),
          onFallback: activateTextRenderer,
        });
        await renderer.initialize(host);
        if (!active) return;
        if (pausedRef.current) renderer.pause();
        await coordinator.playPixi();
      } catch (error) {
        if (!active || controller.signal.aborted) return;
        if (coordinator?.hasCheckpointFailure()) {
          reportFailure(error);
          return;
        }
        try {
          if (coordinator) {
            await coordinator.activateTextFallback();
          } else {
            await activateTextRenderer();
            await playPresentationPlan(textRenderer, request, {
              signal: controller.signal,
              startCueIndex,
              onPrepareProgress: reportProgress,
              onCueRendered: (cue) => runtime.handleRenderedCue(cue, request.plan.worldId),
              onCueComplete: (cue) => active ? checkpointRef.current?.(cue) : undefined,
            });
          }
        } catch (fallbackError) {
          reportFailure(fallbackError);
        }
      }
    })();

    return () => {
      active = false;
      clearTimeout(transitionTimer);
      clearTimeout(progressTimer);
      controller.abort();
      runtime.skipDialogue(true);
      renderer?.dispose();
      textRenderer.dispose();
      rendererRef.current = null;
    };
  }, [checkpointRef, pausedRef, progressRef, request, runtime, startCueIndex]);

  useEffect(() => {
    if (paused) {
      rendererRef.current?.pause();
      runtime.pause();
    } else {
      rendererRef.current?.resume();
      runtime.resume();
    }
  }, [paused, runtime]);

  useEffect(() => {
    if (skipVersion !== skipVersionRef.current) {
      rendererRef.current?.skip();
      runtime.skipDialogue();
    }
    skipVersionRef.current = skipVersion;
  }, [runtime, skipVersion]);

  const loading = resolveWorldLoadingPresentation({
    elapsedMs: loadingElapsedMs,
    loaded: assetProgress.loaded,
    total: assetProgress.total,
  });

  return (
    <div className="absolute inset-0 overflow-hidden bg-[#151816]" data-testid="world-stage">
      <div ref={hostRef} className="absolute inset-0" data-testid="world-stage-canvas-host" />
      {preparing && loading.kind !== "hidden" ? (
        <div className="absolute inset-0 z-10 grid place-items-center bg-[#151816]/90 px-8 text-center" data-testid="world-stage-loading" aria-busy="true">
          <div className="w-[min(420px,100%)]">
            <p className="m-0 font-serif text-2xl text-white/90">正在显影</p>
            {loading.kind === "progress" ? (
              <>
                <div className="mt-7 h-1 overflow-hidden bg-white/10" role="progressbar" aria-valuemin={0} aria-valuemax={loading.total || 1} aria-valuenow={loading.loaded}>
                  <div className="h-full bg-[#C98B65] transition-[width] duration-300" style={{ width: `${loading.ratio * 100}%` }} />
                </div>
                <p className="m-0 mt-3 text-xs text-white/45">{loading.loaded} / {loading.total}</p>
              </>
            ) : null}
          </div>
        </div>
      ) : null}
      {fallback ? <div className="absolute inset-0 grid place-items-center bg-[#151816] px-[max(10vw,32px)] text-center" data-testid="world-stage-text-fallback"><p className="m-0 max-w-3xl font-serif text-xl leading-9 text-white/75">{fallback.text}</p></div> : null}
      {presentationError ? <div className="absolute inset-x-4 bottom-4 z-10 rounded-md border border-[#E9C8B6] bg-[#3A2520]/95 px-4 py-3 text-sm text-[#FFE8DB]" data-testid="world-stage-error" role="alert">{presentationError}</div> : null}
    </div>
  );
}
