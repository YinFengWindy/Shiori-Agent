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
    const textRenderer = new TextWorldPresentationRenderer((snapshot) => {
      if (active) setFallback(snapshot);
    });

    const activateTextFallback = async () => {
      if (!active || renderer?.kind === "text") return;
      renderer?.dispose();
      renderer = textRenderer;
      rendererRef.current = renderer;
      await renderer.initialize(host);
      await playPresentationPlan(renderer, request, { signal: controller.signal });
    };

    void (async () => {
      try {
        const module = await import("./pixiWorldPresentationRenderer") as PixiRendererModule;
        if (!active) return;
        renderer = module.createPixiWorldPresentationRenderer({ onContextLoss: () => void activateTextFallback() });
        rendererRef.current = renderer;
        await renderer.initialize(host);
        if (!active) return;
        if (pausedRef.current) renderer.pause();
        await playPresentationPlan(renderer, request, {
          signal: controller.signal,
          startCueIndex,
          onCueComplete: (cue) => checkpointRef.current?.(cue),
        });
      } catch {
        if (!controller.signal.aborted) await activateTextFallback();
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
    </div>
  );
}
