import { useEffect, useMemo, useRef, useState } from "react";
import { useLatestRef } from "../shared/useLatestRef";
import type { PerformancePlan, PresentationCue } from "./presentationProtocol";
import { WorldVoicePlayback, type WorldVoiceCue, type WorldVoiceProfile } from "./worldVoicePlayback";
import {
  createWorldAssetManifest,
  playPresentationPlan,
  TextWorldPresentationRenderer,
  type TextPresentationSnapshot,
  type WorldPresentationPrepareRequest,
  type WorldPresentationRenderer,
} from "./worldPresentationRenderer";
import type { WorldVoiceAudio } from "./worldVoicePlayback";

type WorldStageProps = {
  plan: PerformancePlan;
  preloadPlan?: PerformancePlan;
  fallbackText: string;
  initialVisual?: { id: string; url: string };
  startCueIndex?: number;
  paused?: boolean;
  skipVersion?: number;
  synthesizeVoice?: (text: string, voiceProfile: Record<string, unknown>, signal: AbortSignal) => Promise<{ audioBase64: string; format: "mp3" }>;
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
  onCueRendered?: (cue: PresentationCue) => Promise<void> | void;
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
    onCueRendered: options.onCueRendered,
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

function voiceCueForPresentation(cue: PresentationCue, worldId: string): WorldVoiceCue | null {
  if (cue.kind !== "dialogue") return null;
  const text = cue.payload.content ?? cue.payload.text;
  if (typeof text !== "string") return null;
  const profile = cue.payload.voiceProfile;
  return {
    cueId: cue.cueId,
    worldId,
    text,
    voiceProfile: typeof profile === "object" && profile !== null && !Array.isArray(profile)
      ? profile as WorldVoiceProfile
      : null,
  };
}

function createBrowserVoiceAudio(audioBase64: string, _format: "mp3"): WorldVoiceAudio {
  const audio = new Audio(`data:audio/mpeg;base64,${audioBase64}`);
  let onended: (() => void) | null = null;
  let onerror: ((event: unknown) => void) | null = null;
  audio.onended = () => onended?.();
  audio.onerror = (event) => onerror?.(event);
  return {
    get onended() {
      return onended;
    },
    set onended(handler) {
      onended = handler;
    },
    get onerror() {
      return onerror;
    },
    set onerror(handler) {
      onerror = handler;
    },
    get src() {
      return audio.src;
    },
    set src(value) {
      audio.src = value;
    },
    play: () => audio.play(),
    pause: () => audio.pause(),
    load: () => audio.load(),
  };
}

/** Thin React host that owns playback controls while adapters own rendering details. */
export function WorldStage({ plan, preloadPlan, fallbackText, initialVisual, startCueIndex = 0, paused = false, skipVersion = 0, synthesizeVoice, onCueComplete }: WorldStageProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<WorldPresentationRenderer | null>(null);
  const checkpointRef = useLatestRef(onCueComplete);
  const skipVersionRef = useRef(skipVersion);
  const pausedRef = useLatestRef(paused);
  const voicePlaybackRef = useRef<WorldVoicePlayback | null>(null);
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
    const voicePlayback = synthesizeVoice ? new WorldVoicePlayback({
      synthesize: (text, profile, signal) => synthesizeVoice(text, profile as Record<string, unknown>, signal),
      createAudio: createBrowserVoiceAudio,
    }) : null;
    voicePlaybackRef.current = voicePlayback;

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
          onCueRendered: (cue) => {
            const voiceCue = voiceCueForPresentation(cue, request.plan.worldId);
            if (voiceCue) void voicePlayback?.playCue(voiceCue);
          },
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
              onCueRendered: (cue) => {
                const voiceCue = voiceCueForPresentation(cue, request.plan.worldId);
                if (voiceCue) void voicePlayback?.playCue(voiceCue);
              },
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
      voicePlayback?.dispose();
      voicePlaybackRef.current = null;
      renderer?.dispose();
      textRenderer.dispose();
      rendererRef.current = null;
    };
  }, [checkpointRef, pausedRef, request, startCueIndex, synthesizeVoice]);

  useEffect(() => {
    if (paused) {
      rendererRef.current?.pause();
      voicePlaybackRef.current?.pause();
    } else {
      rendererRef.current?.resume();
      voicePlaybackRef.current?.resume();
    }
  }, [paused]);

  useEffect(() => {
    if (skipVersion !== skipVersionRef.current) rendererRef.current?.skip();
    if (skipVersion !== skipVersionRef.current) voicePlaybackRef.current?.skip();
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
