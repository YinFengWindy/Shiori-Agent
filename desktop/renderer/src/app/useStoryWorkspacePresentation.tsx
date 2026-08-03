import { useCallback, useState } from "react";
import type { RoleRecord } from "../shared/types";
import type { StoryBridgeClient } from "../story/storyBridgeClient";
import type { useStoryController } from "../story/useStoryController";
import { useStoryCreationFlowController } from "./useStoryCreationFlowController";
import { useStoryPresentationOperation } from "./useStoryPresentationOperation";
import { StoryWorkspacePresentationView } from "./StoryWorkspacePresentationView";
import type { StoryPresentationMode } from "./storyPresentationModes";

type Args = {
  roles: RoleRecord[];
  client: StoryBridgeClient;
  controller: ReturnType<typeof useStoryController>;
  onExit: () => void;
};

/** Assembles the desktop workspace around the direct Story bridge. */
export function useStoryWorkspacePresentation({ roles, client, controller, onExit }: Args) {
  const [mode, setMode] = useState<StoryPresentationMode>("launcher");
  const [loadingStoryId, setLoadingStoryId] = useState("");
  const [loadingElapsedMs, setLoadingElapsedMs] = useState(0);
  const [settingsReturnMode, setSettingsReturnMode] = useState<"launcher" | "game" | "archive">("launcher");
  const operation = useStoryPresentationOperation();
  const { clearError, reportError, run } = operation;
  const { loadStory } = controller;

  const loadStoryForPlay = useCallback(async (storyId: string) => {
    setLoadingStoryId(storyId);
    clearError();
    setLoadingElapsedMs(0);
    const transitionTimer = setTimeout(() => {
      setLoadingElapsedMs(250);
      setMode("loading");
    }, 250);
    const progressTimer = setTimeout(() => setLoadingElapsedMs(2_000), 2_000);
    try {
      if (await loadStory(storyId)) {
        setMode("game");
        return;
      }
      reportError("无法加载这段剧情，请稍后重试。");
      setMode("launcher");
    } finally {
      clearTimeout(transitionTimer);
      clearTimeout(progressTimer);
    }
  }, [clearError, loadStory, reportError]);

  const creation = useStoryCreationFlowController({ client, controller, loadStoryForPlay, run });
  const openSettings = useCallback((returnMode: "launcher" | "game" | "archive") => {
    setSettingsReturnMode(returnMode);
    setMode("settings");
  }, []);
  const closeSettings = useCallback(() => setMode(settingsReturnMode), [settingsReturnMode]);

  return {
    content: <StoryWorkspacePresentationView roles={roles} mode={mode} loadingStoryId={loadingStoryId} loadingElapsedMs={loadingElapsedMs} controller={controller} operation={operation} creation={creation} setMode={setMode} loadStoryForPlay={loadStoryForPlay} onOpenSettings={openSettings} onCloseSettings={closeSettings} onExit={onExit} />,
  };
}
