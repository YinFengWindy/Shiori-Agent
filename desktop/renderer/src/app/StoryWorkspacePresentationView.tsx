import type { RoleRecord } from "../shared/types";
import { toFileUrl } from "../shared/format";
import { StoryArchiveSurface, StoryCreateFlow, StoryGameSurface, StoryLauncher, StoryLoadList, StoryLoadingScreen, StorySettings } from "../story";
import type { useStoryController } from "../story/useStoryController";
import type { useStoryCreationFlowController } from "./useStoryCreationFlowController";
import type { useStoryPresentationOperation } from "./useStoryPresentationOperation";
import type { StoryPresentationMode } from "./storyPresentationModes";

/** Story state required by the presentation router. */
export type StoryWorkspacePresentationController = Pick<ReturnType<typeof useStoryController>, "story" | "stories" | "loading" | "error" | "busy" | "reloadStories" | "submitInput">;

/** Operation state required by Story routes. */
export type StoryOperationPresentationController = Pick<ReturnType<typeof useStoryPresentationOperation>, "error" | "busy" | "clearError">;

/** Creation state consumed by the Story launcher route. */
export type StoryCreationPresentationController = Pick<ReturnType<typeof useStoryCreationFlowController>, "createStory">;

type Props = {
  roles: RoleRecord[];
  mode: StoryPresentationMode;
  loadingStoryId: string;
  loadingElapsedMs: number;
  controller: StoryWorkspacePresentationController;
  operation: StoryOperationPresentationController;
  creation: StoryCreationPresentationController;
  setMode: (mode: StoryPresentationMode) => void;
  loadStoryForPlay: (storyId: string) => Promise<void>;
  onOpenSettings: (returnMode: "launcher" | "game" | "archive") => void;
  onCloseSettings: () => void;
  onExit: () => void;
};

/** Routes launcher, Story creation, play, archive, and preferences surfaces. */
export function StoryWorkspacePresentationView({ roles, mode, loadingStoryId, loadingElapsedMs, controller, operation, creation, setMode, loadStoryForPlay, onOpenSettings, onCloseSettings, onExit }: Props) {
  const story = controller.story;
  const error = operation.error || controller.error;
  const busy = operation.busy || controller.busy;
  const storyRoles = roles.map((role) => ({
    id: role.id,
    name: role.name,
    description: role.description,
    avatarUrl: role.avatar_abs ? toFileUrl(role.avatar_abs) : undefined,
  }));

  if (mode === "launcher" && controller.loading) {
    return <StoryLoadingScreen mode="listing" error={error} onRetry={() => void controller.reloadStories()} onBack={onExit} />;
  }
  if (mode === "launcher") {
    return <StoryLauncher roles={roles} busy={busy} error={error} onCreateStory={() => { operation.clearError(); setMode("create"); }} onOpenLoad={() => { operation.clearError(); setMode("load"); }} onOpenSettings={() => { operation.clearError(); onOpenSettings("launcher"); }} onExit={onExit} />;
  }
  if (mode === "load") {
    return <StoryLoadList stories={controller.stories} busy={busy} error={error} onBack={() => setMode("launcher")} onLoadStory={(storyId) => void loadStoryForPlay(storyId)} />;
  }
  if (mode === "loading") {
    return <StoryLoadingScreen mode="story" busy={busy} error={error} elapsedMs={loadingElapsedMs} loaded={0} total={1} onRetry={loadingStoryId ? () => void loadStoryForPlay(loadingStoryId) : undefined} onBack={() => setMode("launcher")} />;
  }
  if (mode === "settings") {
    return <StorySettings onBack={onCloseSettings} />;
  }
  if (mode === "create" || !story) {
    return <StoryCreateFlow roles={storyRoles} busy={operation.busy} error={error} onBack={() => setMode("launcher")} onCreate={creation.createStory} />;
  }
  if (mode === "archive") {
    return <StoryArchiveSurface story={story} busy={busy} error={error} onSubmitInput={controller.submitInput} onOpenSettings={() => onOpenSettings("archive")} onExit={() => setMode("launcher")} />;
  }
  const storyCharacter = roles.find((role) => role.id === story.roleSnapshot.id);
  return <StoryGameSurface story={story} busy={busy} error={error} characterAvatarUrl={storyCharacter?.avatar_abs ? toFileUrl(storyCharacter.avatar_abs) : undefined} onSubmitInput={controller.submitInput} onOpenArchive={() => setMode("archive")} onOpenSettings={() => onOpenSettings("game")} onExit={() => setMode("launcher")} />;
}
