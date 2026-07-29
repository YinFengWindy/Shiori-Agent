import type {
  BackfillPreview,
  DecisionBarrier,
  NativeIdentityDraft,
  SceneShot,
  WorldCatchUp,
  WorldCreationDraft,
  WorldCreationInput,
  WorldDetails,
  WorldSummary,
  WorldTimelineEntry,
} from "./types";
import {
  parsePresentationState,
  parseWorldCatchUpPerformance,
  parseWorldDetailsPerformance,
  type WorldPresentationState,
} from "./presentationProtocol";
import { WorldBridgeError } from "./types";

type DesktopInvoke = typeof window.miraDesktop.invoke;

async function invokePayload<T>(invoke: DesktopInvoke, method: string, payload: Record<string, unknown>) {
  const response = await invoke({ method, payload });
  if (response.error) {
    throw new WorldBridgeError(response.error.message, response.error.code);
  }
  return response.payload as T;
}

/** Typed renderer contract for the persistent-world desktop bridge. */
export interface WorldBridgeClient {
  listWorlds(): Promise<WorldSummary[]>;
  getWorld(worldId: string): Promise<WorldDetails>;
  previewDraft(input: WorldCreationInput): Promise<WorldCreationDraft>;
  confirmDraft(draftId: string, identities: NativeIdentityDraft[]): Promise<WorldDetails>;
  addOc(worldId: string, oc: WorldCreationInput["firstOc"], anchorId?: string): Promise<WorldDetails>;
  switchOc(worldId: string, ocId: string): Promise<WorldDetails>;
  submitAction(worldId: string, content: string): Promise<void>;
  advance(worldId: string): Promise<void>;
  resolveBarrier(worldId: string, barrier: DecisionBarrier, choiceId: string): Promise<WorldDetails>;
  getTimeline(worldId: string, perspective: "known" | "omniscient", ocId?: string): Promise<WorldTimelineEntry[]>;
  copyWorld(worldId: string, anchorId: string): Promise<WorldDetails>;
  previewBackfill(worldId: string, anchorId: string, oc: WorldCreationInput["firstOc"]): Promise<BackfillPreview>;
  commitBackfill(worldId: string, preview: BackfillPreview): Promise<WorldDetails>;
  cancelRun(worldId: string): Promise<WorldDetails>;
  catchUp(worldId: string, cursor?: string): Promise<WorldCatchUp>;
  pausePresentation(worldId: string): Promise<WorldPresentationState>;
  resumePresentation(worldId: string): Promise<WorldPresentationState>;
  checkpointPresentation(worldId: string, planId: string, cueIndex: number): Promise<WorldPresentationState>;
  redrawShot(worldId: string, shotId: string): Promise<SceneShot>;
}

/** Creates a world client over the preload API without exposing bridge payloads to views. */
export function createWorldBridgeClient(invoke: DesktopInvoke = window.miraDesktop.invoke): WorldBridgeClient {
  return {
    async listWorlds() {
      const payload = await invokePayload<{ worlds: WorldSummary[] }>(invoke, "worlds.list", {});
      return payload.worlds;
    },
    async getWorld(worldId) {
      return parseWorldDetailsPerformance((await invokePayload<{ world: WorldDetails }>(invoke, "worlds.get", { world_id: worldId })).world);
    },
    async previewDraft(input) {
      return (await invokePayload<{ draft: WorldCreationDraft }>(invoke, "worlds.drafts.preview", input)).draft;
    },
    async confirmDraft(draftId, identities) {
      return parseWorldDetailsPerformance((await invokePayload<{ world: WorldDetails }>(invoke, "worlds.drafts.confirm", {
        draft_id: draftId,
        native_identities: identities,
      })).world);
    },
    async addOc(worldId, oc, anchorId) {
      return parseWorldDetailsPerformance((await invokePayload<{ world: WorldDetails }>(invoke, "worlds.ocs.add", {
        world_id: worldId,
        oc,
        anchor_id: anchorId,
      })).world);
    },
    async switchOc(worldId, ocId) {
      return parseWorldDetailsPerformance((await invokePayload<{ world: WorldDetails }>(invoke, "worlds.ocs.switch", {
        world_id: worldId,
        oc_id: ocId,
      })).world);
    },
    async submitAction(worldId, content) {
      await invokePayload(invoke, "worlds.actions.submit", { world_id: worldId, content });
    },
    async advance(worldId) {
      await invokePayload(invoke, "worlds.advance", { world_id: worldId });
    },
    async resolveBarrier(worldId, barrier, choiceId) {
      return parseWorldDetailsPerformance((await invokePayload<{ world: WorldDetails }>(invoke, "worlds.barriers.resolve", {
        world_id: worldId,
        barrier_id: barrier.id,
        choice_id: choiceId,
      })).world);
    },
    async getTimeline(worldId, perspective, ocId) {
      const payload = await invokePayload<{ entries: WorldTimelineEntry[] }>(invoke, "worlds.timeline", {
        world_id: worldId,
        perspective,
        oc_id: ocId,
      });
      return payload.entries;
    },
    async copyWorld(worldId, anchorId) {
      return parseWorldDetailsPerformance((await invokePayload<{ world: WorldDetails }>(invoke, "worlds.copy", {
        world_id: worldId,
        anchor_id: anchorId,
      })).world);
    },
    async previewBackfill(worldId, anchorId, oc) {
      return (await invokePayload<{ preview: BackfillPreview }>(invoke, "worlds.backfill.preview", {
        world_id: worldId,
        anchor_id: anchorId,
        oc,
      })).preview;
    },
    async commitBackfill(worldId, preview) {
      return parseWorldDetailsPerformance((await invokePayload<{ world: WorldDetails }>(invoke, "worlds.backfill.commit", {
        world_id: worldId,
        preview,
      })).world);
    },
    async cancelRun(worldId) {
      return parseWorldDetailsPerformance((await invokePayload<{ world: WorldDetails }>(invoke, "worlds.runs.cancel", { world_id: worldId })).world);
    },
    async catchUp(worldId, cursor) {
      return parseWorldCatchUpPerformance(await invokePayload<WorldCatchUp>(invoke, "worlds.events.catch_up", { world_id: worldId, cursor }));
    },
    async pausePresentation(worldId) {
      return parsePresentationState((await invokePayload<{ presentation: WorldPresentationState }>(invoke, "worlds.presentation.pause", { world_id: worldId })).presentation);
    },
    async resumePresentation(worldId) {
      return parsePresentationState((await invokePayload<{ presentation: WorldPresentationState }>(invoke, "worlds.presentation.resume", { world_id: worldId })).presentation);
    },
    async checkpointPresentation(worldId, planId, cueIndex) {
      return parsePresentationState((await invokePayload<{ presentation: WorldPresentationState }>(invoke, "worlds.presentation.checkpoint", {
        world_id: worldId,
        plan_id: planId,
        cue_index: cueIndex,
      })).presentation);
    },
    async redrawShot(worldId, shotId) {
      return (await invokePayload<{ shot: SceneShot }>(invoke, "worlds.shots.redraw", {
        world_id: worldId,
        shot_id: shotId,
      })).shot;
    },
  };
}
