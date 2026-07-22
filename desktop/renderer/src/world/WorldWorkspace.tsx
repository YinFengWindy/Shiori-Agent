import type { WorldDetails, WorldSummary } from "./types";
import { WorldScenePanel } from "./WorldScenePanel";
import { WorldStatusSidebar } from "./WorldStatusSidebar";
import { WorldWorkspaceSidebar } from "./WorldWorkspaceSidebar";
import { selectActiveOc } from "./selectors";

type WorldWorkspaceProps = {
  worlds: WorldSummary[];
  world: WorldDetails;
  busy?: boolean;
  error?: string;
  onSelectWorld: (worldId: string) => void;
  onSwitchOc: (ocId: string) => void;
  onCreateWorld: () => void;
  onOpenTimeline: () => void;
  onOpenFocus: () => void;
  onSubmitAction: (content: string) => Promise<boolean>;
  onAdvance: () => void;
  onResolveBarrier: Parameters<typeof WorldScenePanel>[0]["onResolveBarrier"];
  onCancel: () => void;
  onRedrawShot: (shotId: string) => void;
};

/** Renders the persistent-world three-column workspace. */
export function WorldWorkspace({ worlds, world, busy = false, error = "", onSelectWorld, onSwitchOc, onCreateWorld, onOpenTimeline, onOpenFocus, onSubmitAction, onAdvance, onResolveBarrier, onCancel, onRedrawShot }: WorldWorkspaceProps) {
  return (
    <section className="relative grid h-full min-h-0 grid-cols-[220px_minmax(420px,1fr)_260px] overflow-hidden bg-[#F8F8F6]" data-testid="world-workspace">
      <WorldWorkspaceSidebar worlds={worlds} world={world} onSelectWorld={onSelectWorld} onSwitchOc={onSwitchOc} onCreateWorld={onCreateWorld} />
      <WorldScenePanel world={world} busy={busy} onSubmitAction={onSubmitAction} onAdvance={onAdvance} onResolveBarrier={onResolveBarrier} onRedrawShot={onRedrawShot} />
      <WorldStatusSidebar world={world} activeOc={selectActiveOc(world)} onOpenTimeline={onOpenTimeline} onOpenFocus={onOpenFocus} onCancel={onCancel} />
      {error ? <div className="absolute bottom-4 left-1/2 z-20 -translate-x-1/2 rounded-md bg-[#793F36] px-4 py-2 text-sm text-white shadow-lg" role="alert">{error}</div> : null}
    </section>
  );
}
