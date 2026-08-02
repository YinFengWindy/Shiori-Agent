import { useCallback, useState } from "react";
import type { RoleRecord } from "../shared/types";
import type { WorldBridgeClient } from "../world/bridgeClient";
import type { useWorldWorkspaceController } from "../world/useWorldWorkspaceController";
import { useWorldCreationFlowController } from "./useWorldCreationFlowController";
import { useWorldPresentationOperation } from "./useWorldPresentationOperation";
import { WorldWorkspacePresentationView } from "./WorldWorkspacePresentationView";
import type { WorldPresentationMode } from "./worldPresentationModes";

type UseWorldWorkspacePresentationArgs = {
  roles: RoleRecord[];
  client: WorldBridgeClient;
  controller: ReturnType<typeof useWorldWorkspaceController>;
  onExit: () => void;
};

/** Assembles the retained desktop workspace around the Story bridge. */
export function useWorldWorkspacePresentation({ roles, client, controller, onExit }: UseWorldWorkspacePresentationArgs) {
  const [mode, setMode] = useState<WorldPresentationMode>("launcher");
  const [loadingWorldId, setLoadingWorldId] = useState("");
  const [loadingElapsedMs, setLoadingElapsedMs] = useState(0);
  const [settingsReturnMode, setSettingsReturnMode] = useState<"launcher" | "day">("launcher");
  const operation = useWorldPresentationOperation();
  const { clearError, reportError, run } = operation;
  const { loadWorld } = controller;

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
        setMode("day");
        return;
      }
      reportError("无法加载这段剧情，请稍后重试。");
      setMode("launcher");
    } finally {
      clearTimeout(transitionTimer);
      clearTimeout(progressTimer);
    }
  }, [clearError, loadWorld, reportError]);

  const creation = useWorldCreationFlowController({
    client,
    controller,
    loadWorldForPlay,
    run,
  });
  const openSettings = useCallback((returnMode: "launcher" | "day") => {
    setSettingsReturnMode(returnMode);
    setMode("settings");
  }, []);

  const closeSettings = useCallback(() => {
    setMode(settingsReturnMode);
  }, [settingsReturnMode]);

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
        setMode={setMode}
        loadWorldForPlay={loadWorldForPlay}
        onOpenSettings={openSettings}
        onCloseSettings={closeSettings}
        onExit={onExit}
      />
    ),
  };
}
