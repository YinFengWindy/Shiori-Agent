import { useStoryGalleryRefresh } from "./useStoryGalleryRefresh";
import { useCallback, useState } from "react";
import type { RoleRecord } from "@yinfengwindy/shiori-sdk";
import type { StoryBridgeClient } from "./storyBridgeClient";
import type { StoryCgGallery } from "./types";
import { isStoryOpeningFailed, replaceStoryGallery } from "./selectors";
import type { useStoryController } from "./useStoryController";
import { waitForMinimumStoryLoadingStage, waitForStoryLoadingCompletion } from "./storyLoadingPresentation";
import { useStoryCreationFlowController } from "./useStoryCreationFlowController";
import { useStoryPresentationOperation } from "./useStoryPresentationOperation";
import { StoryWorkspacePresentationView } from "./StoryWorkspacePresentationView";
import type { StoryPresentationMode } from "./storyPresentationModes";
import type { StoryGameplayLoadingPhase } from "./storyLoadingPresentation";

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

  const loadStoryForPlay = useCallback(async (storyId: string, options: { keepCurrentSurface?: boolean } = {}) => {
    const keepCurrentSurface = options.keepCurrentSurface === true;
    const startedAt = Date.now();
    setLoadingStoryId(storyId);
    clearError();
    setLoadingElapsedMs(0);
    setLoadingPhase("reading-story");
    const transitionTimer = keepCurrentSurface ? undefined : setTimeout(() => {
      setLoadingElapsedMs(250);
      setMode("loading");
    }, 250);
    const progressTimer = setTimeout(() => setLoadingElapsedMs(2_000), 2_000);
    try {
      const loadedStory = await loadStory(storyId);
      if (!loadedStory) {
        if (keepCurrentSurface) throw new Error("无法读取已创建的剧情，请重试。");
        setLoadingElapsedMs(250);
        setMode("loading");
        return;
      }
      await waitForMinimumStoryLoadingStage(startedAt);
      setLoadingPhase("restoring-progress");
      const restoringStartedAt = Date.now();
      const readyStory = await waitForStoryReady(storyId, loadedStory);
      if (isStoryOpeningFailed(readyStory)) throw new Error("开场生成失败，请重试。");
      await waitForMinimumStoryLoadingStage(restoringStartedAt);
      setLoadingPhase("preparing-opening");
      await waitForMinimumStoryLoadingStage(Date.now());
      setLoadingPhase("opening-ready");
      await waitForStoryLoadingCompletion();
      setMode("game");
    } catch (error) {
      if (keepCurrentSurface) throw error instanceof Error ? error : new Error("无法加载这段剧情，请重试。");
      reportError(error, "剧情加载失败，请重试");
      setLoadingElapsedMs(250);
      setMode("loading");
    } finally {
      if (transitionTimer !== undefined) clearTimeout(transitionTimer);
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
  useStoryGalleryRefresh(mode === "gallery", refreshCgGallery, reportError);
  const openCgGallery = useCallback(() => {
    clearError();
    setMode("gallery");
    setCgGalleryLoading(true);
    void refreshCgGallery().catch((error: unknown) => {
      reportError(error, "CG 集加载失败，请重试");
    }).finally(() => setCgGalleryLoading(false));
  }, [clearError, refreshCgGallery, reportError]);
  const retryCg = useCallback((storyId: string, resourceId: string) => {
    void run(
      () => client.retryCg(storyId, resourceId),
      (story) => setCgGallery((current) => replaceStoryGallery(current, story)),
    );
  }, [client, run]);

  return {
    content: <StoryWorkspacePresentationView roles={roles} mode={mode} loadingStoryId={loadingStoryId} loadingElapsedMs={loadingElapsedMs} loadingPhase={loadingPhase} cgGallery={cgGallery} cgGalleryLoading={cgGalleryLoading} controller={controller} operation={operation} creation={creation} setMode={setMode} loadStoryForPlay={loadStoryForPlay} onOpenCg={openCgGallery} onRetryCg={retryCg} onOpenSettings={openSettings} onCloseSettings={closeSettings} onExit={onExit} />,
  };
}
