import { useCallback, useEffect, useState } from "react";
import type { RoleRecord } from "../shared/types";
import type { StoryBridgeClient } from "../story/storyBridgeClient";
import type { StoryCgGallery } from "../story/types";
import type { useStoryController } from "../story/useStoryController";
import { waitForMinimumStoryLoadingStage, waitForStoryLoadingCompletion } from "../story/storyLoadingPresentation";
import { useStoryCreationFlowController } from "./useStoryCreationFlowController";
import { useStoryPresentationOperation } from "./useStoryPresentationOperation";
import { StoryWorkspacePresentationView } from "./StoryWorkspacePresentationView";
import type { StoryPresentationMode } from "./storyPresentationModes";
import type { StoryGameplayLoadingPhase } from "../story/storyLoadingPresentation";

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
  const [loadingPhase, setLoadingPhase] = useState<StoryGameplayLoadingPhase>("reading-story");
  const [cgGallery, setCgGallery] = useState<StoryCgGallery[]>([]);
  const [cgGalleryLoading, setCgGalleryLoading] = useState(false);
  const [settingsReturnMode, setSettingsReturnMode] = useState<"launcher" | "game" | "archive">("launcher");
  const operation = useStoryPresentationOperation();
  const { clearError, reportError, run } = operation;
  const { loadStory, waitForStoryReady } = controller;

  const loadStoryForPlay = useCallback(async (storyId: string) => {
    const startedAt = Date.now();
    setLoadingStoryId(storyId);
    clearError();
    setLoadingElapsedMs(0);
    setLoadingPhase("reading-story");
    const transitionTimer = setTimeout(() => {
      setLoadingElapsedMs(250);
      setMode("loading");
    }, 250);
    const progressTimer = setTimeout(() => setLoadingElapsedMs(2_000), 2_000);
    try {
      const loadedStory = await loadStory(storyId);
      if (loadedStory) {
        await waitForMinimumStoryLoadingStage(startedAt);
        setLoadingPhase("restoring-progress");
        const restoringStartedAt = Date.now();
        await waitForStoryReady(storyId, loadedStory);
        await waitForMinimumStoryLoadingStage(restoringStartedAt);
        setLoadingPhase("preparing-opening");
        await waitForMinimumStoryLoadingStage(Date.now());
        setLoadingPhase("opening-ready");
        await waitForStoryLoadingCompletion();
        setMode("game");
        return;
      }
      setLoadingElapsedMs(250);
      setMode("loading");
    } catch (error) {
      reportError(error instanceof Error ? error.message : "Unable to load this Story. Please try again.");
      setLoadingElapsedMs(250);
      setMode("loading");
    } finally {
      clearTimeout(transitionTimer);
      clearTimeout(progressTimer);
    }
  }, [clearError, loadStory, reportError, waitForStoryReady]);

  const creation = useStoryCreationFlowController({ client, controller, loadStoryForPlay, run });
  const openSettings = useCallback((returnMode: "launcher" | "game" | "archive") => {
    setSettingsReturnMode(returnMode);
    setMode("settings");
  }, []);
  const closeSettings = useCallback(() => setMode(settingsReturnMode), [settingsReturnMode]);
  const refreshCgGallery = useCallback(async () => {
    setCgGallery(await client.listCgGallery());
  }, [client]);
  useEffect(() => window.miraDesktop.onEvent((event) => {
    if (mode !== "gallery" || event.method !== "stories.resource.changed") return;
    void refreshCgGallery().catch((error: unknown) => {
      reportError(error instanceof Error ? error.message : "无法刷新 CG 集");
    });
  }), [mode, refreshCgGallery, reportError]);
  const openCgGallery = useCallback(() => {
    clearError();
    setMode("gallery");
    setCgGalleryLoading(true);
    void refreshCgGallery().catch((error: unknown) => {
      reportError(error instanceof Error ? error.message : "无法读取 CG 集");
    }).finally(() => setCgGalleryLoading(false));
  }, [clearError, refreshCgGallery, reportError]);
  const retryCg = useCallback((storyId: string, resourceId: string) => {
    void run(
      () => client.retryCg(storyId, resourceId),
      refreshCgGallery,
    );
  }, [client, refreshCgGallery, run]);

  return {
    content: <StoryWorkspacePresentationView roles={roles} mode={mode} loadingStoryId={loadingStoryId} loadingElapsedMs={loadingElapsedMs} loadingPhase={loadingPhase} cgGallery={cgGallery} cgGalleryLoading={cgGalleryLoading} controller={controller} operation={operation} creation={creation} setMode={setMode} loadStoryForPlay={loadStoryForPlay} onOpenCg={openCgGallery} onRetryCg={retryCg} onOpenSettings={openSettings} onCloseSettings={closeSettings} onExit={onExit} />,
  };
}
