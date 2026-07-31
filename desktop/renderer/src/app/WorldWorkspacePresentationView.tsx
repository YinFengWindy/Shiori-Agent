import type { RoleRecord } from "../shared/types";
import { toFileUrl } from "../shared/format";
import {
  WorldCreateFlow,
  GalgameFocusMode,
  WorldDaySurface,
  WorldGameSettings,
  WorldGameSurface,
  WorldLauncher,
  WorldLoadingScreen,
  WorldTimelineView,
} from "../world";
import type { useWorldWorkspaceController } from "../world/useWorldWorkspaceController";
import type { WorldPresentationRuntime } from "../world/worldPresentationRuntime";
import type { useWorldCreationFlowController } from "./useWorldCreationFlowController";
import type { useWorldPresentationOperation } from "./useWorldPresentationOperation";
import type { useWorldTimelineController } from "./useWorldTimelineController";
import type { WorldPresentationMode } from "./worldPresentationModes";
import { selectWorldScene } from "../world/worldDayPresentation";

type Props = {
  roles: RoleRecord[];
  mode: WorldPresentationMode;
  loadingWorldId: string;
  loadingElapsedMs: number;
  controller: ReturnType<typeof useWorldWorkspaceController>;
  operation: ReturnType<typeof useWorldPresentationOperation>;
  creation: ReturnType<typeof useWorldCreationFlowController>;
  timeline: ReturnType<typeof useWorldTimelineController>;
  runtime: WorldPresentationRuntime;
  activeSceneId: string;
  sceneMode: "live" | "replay";
  setMode: (mode: WorldPresentationMode) => void;
  loadWorldForPlay: (worldId: string) => Promise<void>;
  openScene: (sceneId: string) => void;
  onReturnToDay: (dismissLiveScene: boolean) => void;
  onSceneComplete: () => void;
  onOpenSettings: (returnMode: "launcher" | "day") => void;
  onCloseSettings: () => void;
  onExit: () => void;
};

/** Dispatches World routes without owning bridge or workflow state. */
export function WorldWorkspacePresentationView({ roles, mode, loadingWorldId, loadingElapsedMs, controller, operation, creation, timeline, runtime, activeSceneId, sceneMode, setMode, loadWorldForPlay, openScene, onReturnToDay, onSceneComplete, onOpenSettings, onCloseSettings, onExit }: Props) {
  const world = controller.world;
  const error = operation.error || controller.error;
  const busy = operation.busy || controller.busy;
  const worldRoles = roles.map((role) => ({
    id: role.id,
    name: role.name,
    description: role.description,
    avatarUrl: role.avatar_abs ? toFileUrl(role.avatar_abs) : undefined,
  }));

  if (mode === "launcher" && controller.loading) {
    return <WorldLoadingScreen mode="listing" error={error} onRetry={() => void controller.reloadWorlds()} onBack={onExit} />;
  }
  if (mode === "launcher") {
    return <WorldLauncher worlds={controller.worlds} busy={busy} error={error} onCreateWorld={() => { operation.clearError(); creation.resetDraft(); setMode("create"); }} onLoadWorld={(worldId) => void loadWorldForPlay(worldId)} onOpenSettings={() => { operation.clearError(); onOpenSettings("launcher"); }} onExit={onExit} />;
  }
  if (mode === "loading") {
    return <WorldLoadingScreen mode="world" busy={busy} error={error} elapsedMs={loadingElapsedMs} loaded={0} total={1} onRetry={loadingWorldId ? () => void loadWorldForPlay(loadingWorldId) : undefined} onBack={() => setMode("launcher")} />;
  }
  if (mode === "settings") {
    return <WorldGameSettings onBack={onCloseSettings} />;
  }
  if (mode === "create" || !world) {
    return <WorldCreateFlow roles={worldRoles} initialSeed={creation.seed} busy={operation.busy} draft={creation.draft} onBack={() => setMode("launcher")} onRerollSeed={creation.rerollSeed} onPreview={creation.previewDraft} onConfirm={creation.confirmDraft} />;
  }
  if (mode === "timeline") {
    return <WorldTimelineView worldName={world.name} activeOcName={controller.activeOc?.name ?? "当前 OC"} entries={timeline.timeline} perspective={timeline.perspective} backfillPreview={timeline.backfillPreview} onBack={() => setMode(timeline.returnMode)} onPerspectiveChange={timeline.changePerspective} onCopyWorld={timeline.copyWorld} onPreviewBackfill={timeline.previewBackfill} onCommitBackfill={timeline.commitBackfill} />;
  }
  if (mode === "scene") {
    const scene = selectWorldScene(world, activeSceneId);
    if (sceneMode === "replay" && scene) {
      return <GalgameFocusMode worldName={world.name} beat={scene} onExit={() => onReturnToDay(false)} onRedrawShot={controller.redrawShot} />;
    }
    return <WorldGameSurface world={world} runtime={runtime} busy={busy} onOpenTimeline={() => timeline.open("scene")} onExitWorkspace={() => onReturnToDay(true)} onSceneComplete={onSceneComplete} onResolveBarrier={controller.resolveBarrier} onRedrawShot={controller.redrawShot} onPause={controller.pausePresentation} onResume={controller.resumePresentation} onCheckpoint={controller.checkpointPresentation} />;
  }
  return <WorldDaySurface world={world} busy={busy} error={error} onCompleteDay={controller.completeDay} onReplayScene={openScene} onOpenTimeline={() => timeline.open("day")} onOpenSettings={() => onOpenSettings("day")} onSwitchOc={controller.switchOc} onExit={() => setMode("launcher")} />;
}
