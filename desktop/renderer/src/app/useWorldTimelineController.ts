import { useCallback, useState } from "react";
import type { WorldBridgeClient } from "../world/bridgeClient";
import type { BackfillPreview, WorldCreationInput, WorldDetails } from "../world/types";
import type { useWorldWorkspaceController } from "../world/useWorldWorkspaceController";
import type { RunWorldPresentation } from "./useWorldPresentationOperation";
import type { TimelineReturnMode, WorldPresentationMode } from "./worldPresentationModes";

type Args = {
  client: WorldBridgeClient;
  controller: ReturnType<typeof useWorldWorkspaceController>;
  world: WorldDetails | null;
  loadWorldForPlay: (worldId: string) => Promise<void>;
  run: RunWorldPresentation;
  setMode: (mode: WorldPresentationMode) => void;
};

/** Owns timeline perspective, copy, and historical-backfill operations. */
export function useWorldTimelineController({ client, controller, world, loadWorldForPlay, run, setMode }: Args) {
  const [returnMode, setReturnMode] = useState<TimelineReturnMode>("game");
  const [timeline, setTimeline] = useState<Awaited<ReturnType<WorldBridgeClient["getTimeline"]>>>([]);
  const [perspective, setPerspective] = useState<"known" | "omniscient">("known");
  const [backfillPreview, setBackfillPreview] = useState<BackfillPreview | null>(null);

  const open = useCallback((nextReturnMode: TimelineReturnMode) => {
    if (!world) return;
    setReturnMode(nextReturnMode);
    void run(
      () => client.getTimeline(world.id, perspective, perspective === "known" ? world.activeOcId ?? undefined : undefined),
      (entries) => {
        setTimeline(entries);
        setBackfillPreview(null);
        setMode("timeline");
      },
    );
  }, [client, perspective, run, setMode, world]);

  const changePerspective = useCallback((next: "known" | "omniscient") => {
    if (!world) return;
    setPerspective(next);
    void run(
      () => client.getTimeline(world.id, next, next === "known" ? world.activeOcId ?? undefined : undefined),
      setTimeline,
    );
  }, [client, run, world]);

  const copyWorld = useCallback((anchorId: string) => {
    if (!world) return;
    void run(() => client.copyWorld(world.id, anchorId), async (copied) => {
      await controller.reloadWorlds();
      await loadWorldForPlay(copied.id);
    });
  }, [client, controller, loadWorldForPlay, run, world]);

  const previewBackfill = useCallback((anchorId: string, oc: WorldCreationInput["firstOc"]) => {
    if (world) void run(() => client.previewBackfill(world.id, anchorId, oc), setBackfillPreview);
  }, [client, run, world]);

  const commitBackfill = useCallback((preview: BackfillPreview) => {
    if (!world) return;
    void run(() => client.commitBackfill(world.id, preview), async (updated) => {
      await controller.reloadWorlds();
      await loadWorldForPlay(updated.id);
      setBackfillPreview(null);
    });
  }, [client, controller, loadWorldForPlay, run, world]);

  return { returnMode, timeline, perspective, backfillPreview, open, changePerspective, copyWorld, previewBackfill, commitBackfill };
}
