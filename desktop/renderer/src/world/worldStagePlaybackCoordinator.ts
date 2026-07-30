import type { PresentationCue } from "./presentationProtocol";
import {
  playPresentationPlan,
  type WorldPresentationPrepareRequest,
  type WorldPresentationRenderer,
} from "./worldPresentationRenderer";

export type WorldStagePlaybackCoordinatorOptions = {
  request: WorldPresentationPrepareRequest;
  startCueIndex: number;
  signal?: AbortSignal;
  pixiRenderer: WorldPresentationRenderer;
  textRenderer: WorldPresentationRenderer;
  onCueComplete?: (cue: PresentationCue) => Promise<void> | void;
  onCueRendered?: (cue: PresentationCue) => Promise<void> | void;
  onPrepareProgress?: (loaded: number, total: number) => void;
  onFallback?: () => Promise<void> | void;
};

/** Keeps renderer fallback and durable checkpointing on separate failure paths. */
export function createWorldStagePlaybackCoordinator(options: WorldStagePlaybackCoordinatorOptions) {
  const checkpointedCueIds = new Set<string>();
  const pixiController = new AbortController();
  const textController = new AbortController();
  let nextCueIndex = Math.min(options.request.plan.cues.length, Math.max(0, options.startCueIndex));
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
    onPrepareProgress: options.onPrepareProgress,
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

  return {
    activateTextFallback,
    hasCheckpointFailure: () => checkpointFailed,
    getCheckpointFailure: () => checkpointFailure,
    async playPixi(): Promise<"pixi" | "text"> {
      try {
        await play(options.pixiRenderer, pixiController.signal);
        return "pixi";
      } catch (error) {
        if (options.signal?.aborted || checkpointFailed) throw error;
        await activateTextFallback();
        return "text";
      }
    },
  };
}
