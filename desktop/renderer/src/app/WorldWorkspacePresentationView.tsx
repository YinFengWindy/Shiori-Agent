import type { RoleRecord } from "../shared/types";
import { toFileUrl } from "../shared/format";
import {
  WorldCreateFlow,
  WorldDaySurface,
  WorldGameSettings,
  WorldLauncher,
  WorldLoadingScreen,
} from "../world";
import type { useWorldWorkspaceController } from "../world/useWorldWorkspaceController";
import type { useWorldCreationFlowController } from "./useWorldCreationFlowController";
import type { useWorldPresentationOperation } from "./useWorldPresentationOperation";
import type { WorldPresentationMode } from "./worldPresentationModes";

type Props = {
  roles: RoleRecord[];
  mode: WorldPresentationMode;
  loadingWorldId: string;
  loadingElapsedMs: number;
  controller: ReturnType<typeof useWorldWorkspaceController>;
  operation: ReturnType<typeof useWorldPresentationOperation>;
  creation: ReturnType<typeof useWorldCreationFlowController>;
  setMode: (mode: WorldPresentationMode) => void;
  loadWorldForPlay: (worldId: string) => Promise<void>;
  onOpenSettings: (returnMode: "launcher" | "day") => void;
  onCloseSettings: () => void;
  onExit: () => void;
};

/** Dispatches World routes without owning bridge or workflow state. */
export function WorldWorkspacePresentationView({ roles, mode, loadingWorldId, loadingElapsedMs, controller, operation, creation, setMode, loadWorldForPlay, onOpenSettings, onCloseSettings, onExit }: Props) {
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
  return <WorldDaySurface world={world} busy={busy} error={error} onCompleteDay={controller.completeDay} onOpenSettings={() => onOpenSettings("day")} onExit={() => setMode("launcher")} />;
}
