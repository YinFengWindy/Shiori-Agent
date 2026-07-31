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
  const runtime = useMemo(() => new WorldPresentationRuntime({
    synthesizeVoice: (text, profile, signal) => client.synthesizeVoice(text, profile, signal),
  }), [client]);
  const operation = useWorldPresentationOperation();
  const { clearError, reportError, run } = operation;

  useEffect(() => () => runtime.dispose(), [runtime]);

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
      if (await controller.loadWorld(worldId)) {
        setMode("game");
        return;
      }
      reportError("无法加载这个世界，请稍后重试。");
      setMode("launcher");
    } finally {
      clearTimeout(transitionTimer);
      clearTimeout(progressTimer);
    }
  }, [clearError, controller, reportError]);

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
  const openGame = useCallback(() => {
    if (!controller.world?.scene.beats.length) {
      reportError("当前场景尚无可播放的剧情。");
      return;
    }
    setMode("game");
  }, [controller.world, reportError]);

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
        setMode={setMode}
        loadWorldForPlay={loadWorldForPlay}
        openGame={openGame}
        onExit={onExit}
      />
    ),
  };
}
