import type { ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import type { RoleRecord } from "../shared/types";
import { toFileUrl } from "../shared/format";
import { StoryArchiveSurface, StoryCreateFlow, StoryGameSurface, StoryLauncher, StoryLoadList, StoryLoadingScreen, StorySettings, StoryWorkspaceBackdrop, type StoryWorkspaceBackdropBlur } from "../story";
import { StoryCgGallerySurface } from "../story";
import { useStoryMenuBackground } from "../story/useStoryMenuBackground";
import type { useStoryController } from "../story/useStoryController";
import type { useStoryCreationFlowController } from "./useStoryCreationFlowController";
import type { useStoryPresentationOperation } from "./useStoryPresentationOperation";
import type { StoryPresentationMode } from "./storyPresentationModes";
import type { StoryCgGallery } from "../story/types";
import type { StoryGameplayLoadingPhase } from "../story/storyLoadingPresentation";

/** Story state required by the presentation router. */
export type StoryWorkspacePresentationController = Pick<ReturnType<typeof useStoryController>, "story" | "stories" | "loading" | "loadingPhase" | "error" | "busy" | "reloadStories" | "submitInput">;

/** Operation state required by Story routes. */
export type StoryOperationPresentationController = Pick<ReturnType<typeof useStoryPresentationOperation>, "error" | "busy" | "clearError">;

/** Creation state consumed by the Story launcher route. */
export type StoryCreationPresentationController = Pick<ReturnType<typeof useStoryCreationFlowController>, "createStory">;

function resolveStoryWorkspaceBackdropBlur(mode: StoryPresentationMode): StoryWorkspaceBackdropBlur {
  if (mode === "archive") return "archive";
  if (mode === "load" || mode === "gallery" || mode === "settings" || mode === "create") return "surface";
  return "none";
}

/** Duration used when replacing one Story presentation surface with another. */
export const STORY_PRESENTATION_TRANSITION_SECONDS = 0.42;

type Props = {
  roles: RoleRecord[];
  mode: StoryPresentationMode;
  loadingStoryId: string;
  loadingElapsedMs: number;
  loadingPhase: StoryGameplayLoadingPhase;
  cgGallery: StoryCgGallery[];
  cgGalleryLoading: boolean;
  controller: StoryWorkspacePresentationController;
  operation: StoryOperationPresentationController;
  creation: StoryCreationPresentationController;
  setMode: (mode: StoryPresentationMode) => void;
  loadStoryForPlay: (storyId: string) => Promise<void>;
  onOpenCg: () => void;
  onRetryCg: (storyId: string, resourceId: string) => void;
  onOpenSettings: (returnMode: "launcher" | "game" | "archive") => void;
  onCloseSettings: () => void;
  onExit: () => void;
};

/** Routes launcher, Story creation, play, archive, and preferences surfaces. */
export function StoryWorkspacePresentationView({ roles, mode, loadingStoryId, loadingElapsedMs, loadingPhase, cgGallery, cgGalleryLoading, controller, operation, creation, setMode, loadStoryForPlay, onOpenCg, onRetryCg, onOpenSettings, onCloseSettings, onExit }: Props) {
  const story = controller.story;
  const error = operation.error || controller.error;
  const busy = operation.busy || controller.busy;
  const reducedMotion = useReducedMotion() ?? false;
  const storyMenuBackground = useStoryMenuBackground(roles);
  const presentationKey = mode === "launcher" && controller.loading ? "launcher-loading" : mode;
  const storyRoles = roles.map((role) => ({
    id: role.id,
    name: role.name,
    description: role.description,
    avatarUrl: role.avatar_abs ? toFileUrl(role.avatar_abs) : undefined,
  }));

  let content: ReactNode;
  if (mode === "launcher" && controller.loading) {
    content = <StoryLoadingScreen background={storyMenuBackground} sharedBackdrop mode="listing" phase={controller.loadingPhase} error={error} onRetry={() => void controller.reloadStories()} />;
  } else if (mode === "launcher") {
    content = <StoryLauncher background={storyMenuBackground} sharedBackdrop busy={busy} error={error} onCreateStory={() => { operation.clearError(); setMode("create"); }} onOpenLoad={() => { operation.clearError(); setMode("load"); }} onOpenCg={onOpenCg} onOpenSettings={() => { operation.clearError(); onOpenSettings("launcher"); }} onExit={onExit} />;
  } else if (mode === "load") {
    content = <StoryLoadList stories={controller.stories} background={storyMenuBackground} sharedBackdrop busy={busy} error={error} onBack={() => setMode("launcher")} onLoadStory={(storyId) => void loadStoryForPlay(storyId)} />;
  } else if (mode === "loading") {
    const backgroundReady = story?.id === loadingStoryId && story.backgroundResource?.status !== "generating";
    content = <StoryLoadingScreen background={storyMenuBackground} sharedBackdrop mode="story" phase={loadingPhase} busy={busy} error={error} elapsedMs={loadingElapsedMs} loaded={backgroundReady ? 1 : 0} total={1} onRetry={loadingStoryId ? () => void loadStoryForPlay(loadingStoryId) : undefined} onBack={() => setMode("launcher")} />;
  } else if (mode === "gallery") {
    content = <StoryCgGallerySurface stories={cgGallery} background={storyMenuBackground} sharedBackdrop busy={cgGalleryLoading || busy} error={error} onRetry={onRetryCg} onBack={() => setMode("launcher")} />;
  } else if (mode === "settings") {
    content = <StorySettings background={storyMenuBackground} sharedBackdrop onBack={onCloseSettings} />;
  } else if (mode === "create" || !story) {
    content = <StoryCreateFlow roles={storyRoles} background={storyMenuBackground} sharedBackdrop busy={operation.busy} error={error} onBack={() => setMode("launcher")} onCreate={creation.createStory} />;
  } else if (mode === "archive") {
    content = <StoryArchiveSurface story={story} background={storyMenuBackground} sharedBackdrop error={error} onOpenSettings={() => onOpenSettings("archive")} onExit={() => setMode("launcher")} />;
  } else {
    const storyCharacter = roles.find((role) => role.id === story.roleSnapshot.id);
    content = <StoryGameSurface story={story} background={storyMenuBackground} sharedBackdrop busy={busy} error={error} characterAvatarUrl={storyCharacter?.avatar_abs ? toFileUrl(storyCharacter.avatar_abs) : undefined} onSubmitInput={controller.submitInput} onOpenArchive={() => setMode("archive")} onOpenSettings={() => onOpenSettings("game")} onExit={() => setMode("launcher")} />;
  }

  return <section className="relative h-full min-h-0 overflow-hidden bg-[#1D1520]" data-testid="story-workspace-presentation">
    <StoryWorkspaceBackdrop background={storyMenuBackground} blur={resolveStoryWorkspaceBackdropBlur(mode)} />
    <div className="relative z-10 h-full min-h-0" data-testid="story-presentation-layer">
      <AnimatePresence mode="sync">
        <motion.div
          key={presentationKey}
          className="absolute inset-0"
          data-testid="story-presentation-content"
          data-story-mode={mode}
          data-story-transition-key={presentationKey}
          initial={{ opacity: 0, y: reducedMotion ? 0 : 14 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: reducedMotion ? 0 : -10 }}
          transition={{ duration: reducedMotion ? 0 : STORY_PRESENTATION_TRANSITION_SECONDS, ease: "easeOut" }}
        >
          {content}
        </motion.div>
      </AnimatePresence>
    </div>
  </section>;
}
