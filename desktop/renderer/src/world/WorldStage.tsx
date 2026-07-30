import { useEffect, useMemo, useRef, useState } from "react";
import { useLatestRef } from "../shared/useLatestRef";
import type { PerformancePlan, PresentationCue } from "./presentationProtocol";
import {
  createWorldAssetManifest,
  playPresentationPlan,
  TextWorldPresentationRenderer,
  type TextPresentationSnapshot,
  type WorldPresentationPrepareRequest,
  type WorldPresentationRenderer,
} from "./worldPresentationRenderer";

type WorldStageProps = {
  plan: PerformancePlan;
  preloadPlan?: PerformancePlan;
  fallbackText: string;
  initialVisual?: { id: string; url: string };
  startCueIndex?: number;
  paused?: boolean;
  skipVersion?: number;
  onCueComplete?: (cue: PresentationCue) => Promise<void> | void;
};

type PixiRendererModule = {
  createPixiWorldPresentationRenderer(options: { onContextLoss: () => void }): WorldPresentationRenderer;
};

export type WorldStagePlaybackCoordinatorOptions = {
  request: WorldPresentationPrepareRequest;
  startCueIndex: number;
  signal?: AbortSignal;
  pixiRenderer: WorldPresentationRenderer;
  textRenderer: WorldPresentationRenderer;
  onCueComplete?: (cue: PresentationCue) => Promise<void> | void;
  onFallback?: () => Promise<void> | void;
};

/** Keeps renderer fallback and durable checkpointing on separate failure paths. */
export function createWorldStagePlaybackCoordinator(options: WorldStagePlaybackCoordinatorOptions) {
  const checkpointedCueIds = new Set<string>();
  const pixiController = new AbortController();
  const textController = new AbortController();
  let nextCueIndex = Math.min(
    options.request.plan.cues.length,
    Math.max(0, options.startCueIndex),
  );
  let checkpointFailed = false;
  let checkpointFailure: unknown = null;
  let fallbackPromise: Promise<void> | null = null;

  const abortPlayback = () => {
    pixiController.abort(options.signal?.reason);
    textController.abort(options.signal?.reason);
  };
  if (options.signal?.aborted) abortPlayback();
  else options.signal?.addEventListener("abort", abortPlayback, { once: true });

  const checkpoint = async (cue: PresentationCue) => {
    if (!options.onCueComplete || checkpointedCueIds.has(cue.cueId)) return;
    try {
      await options.onCueComplete(cue);
      checkpointedCueIds.add(cue.cueId);
      nextCueIndex = Math.max(nextCueIndex, cue.sequence + 1);
    } catch (error) {
      checkpointFailed = true;
      checkpointFailure = error;
      throw error;
    }
  };

  const play = (renderer: WorldPresentationRenderer, signal: AbortSignal) => playPresentationPlan(renderer, options.request, {
    signal,
    startCueIndex: nextCueIndex,
    onCueComplete: checkpoint,
  });

  const activateTextFallback = () => {
    if (fallbackPromise) return fallbackPromise;
    if (checkpointFailed || options.signal?.aborted) return Promise.resolve();
    pixiController.abort();
    fallbackPromise = (async () => {
      await options.onFallback?.();
      await play(options.textRenderer, textController.signal);
    })();
    return fallbackPromise;
  };

  const playPixi = async (): Promise<"pixi" | "text"> => {
    try {
      await play(options.pixiRenderer, pixiController.signal);
      return "pixi";
    } catch (error) {
      if (options.signal?.aborted || checkpointFailed) throw error;
      await activateTextFallback();
      return "text";
    }
  };

  return {
    activateTextFallback,
    hasCheckpointFailure: () => checkpointFailed,
    getCheckpointFailure: () => checkpointFailure,
    playPixi,
  };
}

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
  if (initialVisual) {
    manifest.push({ id: initialVisual.id, url: initialVisual.url, kind: "background" });
  }
  return { plan, manifest, initialAssetId: initialVisual?.id, fallbackText };
}

/** Thin React host that owns playback controls while adapters own rendering details. */
export function WorldStage({ plan, preloadPlan, fallbackText, initialVisual, startCueIndex = 0, paused = false, skipVersion = 0, onCueComplete }: WorldStageProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<WorldPresentationRenderer | null>(null);
  const checkpointRef = useLatestRef(onCueComplete);
  const skipVersionRef = useRef(skipVersion);
  const pausedRef = useLatestRef(paused);
  const [fallback, setFallback] = useState<TextPresentationSnapshot | null>(null);
  const [presentationError, setPresentationError] = useState<string | null>(null);
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
    setFallback(null);
    setPresentationError(null);
    const textRenderer = new TextWorldPresentationRenderer((snapshot) => {
      if (active) setFallback(snapshot);
    });

    const reportFailure = (error: unknown) => {
      if (active && !controller.signal.aborted) {
        setPresentationError(error instanceof Error ? error.message : "演出无法继续");
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
        const module = await import("./pixiWorldPresentationRenderer") as PixiRendererModule;
        if (!active) return;
        renderer = module.createPixiWorldPresentationRenderer({
          onContextLoss: () => {
            const fallbackPromise = coordinator?.activateTextFallback();
            if (fallbackPromise) void fallbackPromise.catch(reportFailure);
          },
        });
        rendererRef.current = renderer;
        coordinator = createWorldStagePlaybackCoordinator({
          request,
          startCueIndex,
          signal: controller.signal,
          pixiRenderer: renderer,
          textRenderer,
          onCueComplete: (cue) => active ? checkpointRef.current?.(cue) : undefined,
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
      controller.abort();
      renderer?.dispose();
      textRenderer.dispose();
      rendererRef.current = null;
    };
  }, [checkpointRef, pausedRef, request, startCueIndex]);

  useEffect(() => {
    if (paused) rendererRef.current?.pause();
    else rendererRef.current?.resume();
  }, [paused]);

  useEffect(() => {
    if (skipVersion !== skipVersionRef.current) rendererRef.current?.skip();
    skipVersionRef.current = skipVersion;
  }, [skipVersion]);

  return (
    <div className="absolute inset-0 overflow-hidden bg-[#151816]" data-testid="world-stage">
      <div ref={hostRef} className="absolute inset-0" data-testid="world-stage-canvas-host" />
      {fallback ? (
        <div className="absolute inset-0 grid place-items-center bg-[#151816] px-[max(10vw,32px)] text-center" data-testid="world-stage-text-fallback">
          <p className="m-0 max-w-3xl font-serif text-xl leading-9 text-white/75">{fallback.text}</p>
        </div>
      ) : null}
      {presentationError ? <div className="absolute inset-x-4 bottom-4 z-10 rounded-md border border-[#E9C8B6] bg-[#3A2520]/95 px-4 py-3 text-sm text-[#FFE8DB]" data-testid="world-stage-error" role="alert">{presentationError}</div> : null}
    </div>
  );
}
