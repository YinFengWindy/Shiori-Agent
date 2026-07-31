import { useCallback, useEffect, useState } from "react";
import { selectPendingWorldScene } from "../world/worldDayPresentation";
import type { WorldDetails } from "../world/types";
import type { WorldPresentationMode } from "./worldPresentationModes";

type Args = {
  world: WorldDetails | null;
  mode: WorldPresentationMode;
  setMode: (mode: WorldPresentationMode) => void;
};

/** Owns automatic live-scene entry, replay selection, and Day return semantics. */
export function useWorldSceneNavigation({ world, mode, setMode }: Args) {
  const [activeSceneId, setActiveSceneId] = useState("");
  const [sceneMode, setSceneMode] = useState<"live" | "replay">("live");
  const [dismissedPlanId, setDismissedPlanId] = useState("");
  const pendingScene = selectPendingWorldScene(world);
  const pendingSceneId = pendingScene?.id ?? "";
  const pendingPlanId = world?.presentation?.plans[0]?.planId ?? "";

  useEffect(() => {
    if (mode !== "day" || !pendingSceneId || pendingPlanId === dismissedPlanId) return;
    setActiveSceneId(pendingSceneId);
    setSceneMode("live");
    setMode("scene");
  }, [dismissedPlanId, mode, pendingPlanId, pendingSceneId, setMode]);

  const prepareLoadedWorld = useCallback(() => {
    setDismissedPlanId("");
    setMode("day");
  }, [setMode]);

  const openScene = useCallback((sceneId: string) => {
    const liveScene = selectPendingWorldScene(world);
    setActiveSceneId(sceneId);
    setSceneMode(liveScene?.id === sceneId ? "live" : "replay");
    setMode("scene");
  }, [setMode, world]);

  const returnToDay = useCallback((dismissLiveScene: boolean) => {
    if (dismissLiveScene && pendingPlanId) setDismissedPlanId(pendingPlanId);
    setMode("day");
  }, [pendingPlanId, setMode]);

  const completeLiveScene = useCallback(() => {
    setDismissedPlanId("");
    setMode("day");
  }, [setMode]);

  return {
    activeSceneId,
    sceneMode,
    prepareLoadedWorld,
    openScene,
    returnToDay,
    completeLiveScene,
  };
}
