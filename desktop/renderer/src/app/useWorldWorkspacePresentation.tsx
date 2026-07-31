import { useCallback, useEffect, useMemo, useState } from "react";
import type { RoleRecord } from "../shared/types";
import type { WorldBridgeClient } from "../world/bridgeClient";
import type { useWorldWorkspaceController } from "../world/useWorldWorkspaceController";
import { WorldPresentationRuntime } from "../world/worldPresentationRuntime";
import { useWorldCreationFlowController } from "./useWorldCreationFlowController";
import { useWorldPresentationOperation } from "./useWorldPresentationOperation";
import { useWorldTimelineController } from "./useWorldTimelineController";
import { WorldWorkspacePresentationView } from "./WorldWorkspacePresentationView";
import type { WorldPresentationMode } from "./worldPresentationModes";
import { useWorldSceneNavigation } from "./useWorldSceneNavigation";

type UseWorldWorkspacePresentationArgs = {
  roles: RoleRecord[];
  client: WorldBridgeClient;
  controller: ReturnType<typeof useWorldWorkspaceController>;
  onExit: () => void;
};

/** Assembles route-level World controllers and its persistent presentation runtime. */
export function useWorldWorkspacePresentation({ roles, client, controller, onExit }: UseWorldWorkspacePresentationArgs) {
  const [mode, setMode] = useState<WorldPresentationMode>("launcher");
  const [loadingWorldId, setLoadingWorldId] = useState("");
  const [loadingElapsedMs, setLoadingElapsedMs] = useState(0);
  const [settingsReturnMode, setSettingsReturnMode] = useState<"launcher" | "day">("launcher");
  const runtime = useMemo(() => new WorldPresentationRuntime({
    synthesizeVoice: (text, profile, signal) => client.synthesizeVoice(text, profile, signal),
  }), [client]);
  const operation = useWorldPresentationOperation();
  const { clearError, reportError, run } = operation;
  const { loadWorld } = controller;

  useEffect(() => () => runtime.dispose(), [runtime]);

  const {
    activeSceneId,
    sceneMode,
    prepareLoadedWorld,
    openScene,
    returnToDay,
    completeLiveScene,
  } = useWorldSceneNavigation({ world: controller.world, mode, setMode });

  const loadWorldForPlay = useCallback(async (worldId: string) => {
    setLoadingWorldId(worldId);
    clearError();
    setLoadingElapsedMs(0);
    const transitionTimer = setTimeout(() => {
      setLoadingElapsedMs(250);
      setMode("loading");
    }, 250);
    const progressTimer = setTimeout(() => setLoadingElapsedMs(2_000), 2_000);
    try {
      if (await loadWorld(worldId)) {
        prepareLoadedWorld();
        return;
      }
      reportError("无法加载这个世界，请稍后重试。");
      setMode("launcher");
    } finally {
      clearTimeout(transitionTimer);
      clearTimeout(progressTimer);
    }
  }, [clearError, loadWorld, prepareLoadedWorld, reportError]);

  const creation = useWorldCreationFlowController({
    client,
    controller,
    loadWorldForPlay,
    run,
  });
  const timeline = useWorldTimelineController({
    client,
    controller,
    world: controller.world,
    loadWorldForPlay,
    run,
    setMode,
  });
  const openSettings = useCallback((returnMode: "launcher" | "day") => {
    setSettingsReturnMode(returnMode);
    setMode("settings");
  }, []);

  const closeSettings = useCallback(() => {
    runtime.refreshSettings();
    setMode(settingsReturnMode);
  }, [runtime, settingsReturnMode]);

  return {
    content: (
      <WorldWorkspacePresentationView
        roles={roles}
        mode={mode}
        loadingWorldId={loadingWorldId}
        loadingElapsedMs={loadingElapsedMs}
        controller={controller}
        operation={operation}
        creation={creation}
        timeline={timeline}
        runtime={runtime}
        activeSceneId={activeSceneId}
        sceneMode={sceneMode}
        setMode={setMode}
        loadWorldForPlay={loadWorldForPlay}
        openScene={openScene}
        onReturnToDay={returnToDay}
        onSceneComplete={completeLiveScene}
        onOpenSettings={openSettings}
        onCloseSettings={closeSettings}
        onExit={onExit}
      />
    ),
  };
}
