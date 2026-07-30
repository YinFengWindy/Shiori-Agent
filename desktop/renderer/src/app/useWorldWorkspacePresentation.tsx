import { useCallback, useMemo, useState } from "react";
import { toFileUrl } from "../shared/format";
import type { RoleRecord } from "../shared/types";
import {
  WorldCreateFlow,
  WorldGameSettings as WorldGameSettingsPanel,
  WorldGameSurface,
  WorldLauncher,
  WorldLoadingScreen,
  WorldTimelineView,
  WorldWorkspace,
  type BackfillPreview,
  type NativeIdentityDraft,
  type WorldCreationInput,
} from "../world";
import type { WorldBridgeClient } from "../world/bridgeClient";
import type { useWorldWorkspaceController } from "../world/useWorldWorkspaceController";

type WorldPresentationMode = "launcher" | "game" | "workspace" | "create" | "timeline" | "settings" | "loading";
type TimelineReturnMode = "game" | "workspace";

type UseWorldWorkspacePresentationArgs = {
  roles: RoleRecord[];
  client: WorldBridgeClient;
  controller: ReturnType<typeof useWorldWorkspaceController>;
  onExit: () => void;
};

function createWorldSeed(): string {
  return globalThis.crypto?.randomUUID?.() ?? `seed-${Date.now().toString(36)}`;
}

/** Coordinates world-only presentation modes around the persistent workspace controller. */
export function useWorldWorkspacePresentation({ roles, client, controller, onExit }: UseWorldWorkspacePresentationArgs) {
  const [mode, setMode] = useState<WorldPresentationMode>("launcher");
  const [timelineReturnMode, setTimelineReturnMode] = useState<TimelineReturnMode>("game");
  const [seed, setSeed] = useState(createWorldSeed);
  const [draft, setDraft] = useState<Awaited<ReturnType<WorldBridgeClient["previewDraft"]>> | null>(null);
  const [timeline, setTimeline] = useState<Awaited<ReturnType<WorldBridgeClient["getTimeline"]>>>([]);
  const [perspective, setPerspective] = useState<"known" | "omniscient">("known");
  const [backfillPreview, setBackfillPreview] = useState<BackfillPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [presentationError, setPresentationError] = useState("");
  const [loadingWorldId, setLoadingWorldId] = useState("");

  const worldRoles = useMemo(() => roles.map((role) => ({
    id: role.id,
    name: role.name,
    description: role.description,
    avatarUrl: role.avatar_abs ? toFileUrl(role.avatar_abs) : undefined,
  })), [roles]);
  const world = controller.world;

  const runPresentation = useCallback(async <T,>(operation: () => Promise<T>, apply: (value: T) => Promise<void> | void) => {
    setBusy(true);
    setPresentationError("");
    try {
      const result = await operation();
      await apply(result);
    } catch (error) {
      setPresentationError(error instanceof Error ? error.message : "世界暂时无法响应");
    } finally {
      setBusy(false);
    }
  }, []);

  const openTimeline = useCallback((returnMode: TimelineReturnMode) => {
    if (!world) return;
    setTimelineReturnMode(returnMode);
    void runPresentation(
      () => client.getTimeline(world.id, perspective, perspective === "known" ? world.activeOcId ?? undefined : undefined),
      (entries) => {
        setTimeline(entries);
        setBackfillPreview(null);
        setMode("timeline");
      },
    );
  }, [client, perspective, runPresentation, world]);

  const changePerspective = useCallback((nextPerspective: "known" | "omniscient") => {
    if (!world) return;
    setPerspective(nextPerspective);
    void runPresentation(
      () => client.getTimeline(world.id, nextPerspective, nextPerspective === "known" ? world.activeOcId ?? undefined : undefined),
      setTimeline,
    );
  }, [client, runPresentation, world]);

  const previewDraft = useCallback((input: WorldCreationInput) => {
    void runPresentation(() => client.previewDraft(input), setDraft);
  }, [client, runPresentation]);

  const loadWorldForPlay = useCallback(async (worldId: string) => {
    setLoadingWorldId(worldId);
    setPresentationError("");
    setMode("loading");
    const loaded = await controller.loadWorld(worldId);
    if (loaded) {
      setMode("game");
      return;
    }
    setPresentationError("无法加载这个世界，请稍后重试。");
    setMode("launcher");
  }, [controller]);

  const confirmDraft = useCallback((draftId: string, identities: NativeIdentityDraft[]) => {
    void runPresentation(
      () => client.confirmDraft(draftId, identities),
      async (createdWorld) => {
        setMode("loading");
        await controller.reloadWorlds();
        await loadWorldForPlay(createdWorld.id);
        setDraft(null);
      },
    );
  }, [client, controller, loadWorldForPlay, runPresentation]);

  const copyWorld = useCallback((anchorId: string) => {
    if (!world) return;
    void runPresentation(
      () => client.copyWorld(world.id, anchorId),
      async (copiedWorld) => {
        await controller.reloadWorlds();
        await loadWorldForPlay(copiedWorld.id);
      },
    );
  }, [client, controller, loadWorldForPlay, runPresentation, world]);

  const previewBackfill = useCallback((anchorId: string, oc: WorldCreationInput["firstOc"]) => {
    if (!world) return;
    void runPresentation(() => client.previewBackfill(world.id, anchorId, oc), setBackfillPreview);
  }, [client, runPresentation, world]);

  const commitBackfill = useCallback((preview: BackfillPreview) => {
    if (!world) return;
    void runPresentation(
      () => client.commitBackfill(world.id, preview),
      async (updatedWorld) => {
        await controller.reloadWorlds();
        await loadWorldForPlay(updatedWorld.id);
        setBackfillPreview(null);
      },
    );
  }, [client, controller, loadWorldForPlay, runPresentation, world]);

  const openGame = useCallback(() => {
    if (!world?.scene.beats.length) {
      setPresentationError("当前场景尚无可播放的剧情。");
      return;
    }
    setMode("game");
  }, [world]);

  const content = useMemo(() => {
    const error = presentationError || controller.error;
    if (mode === "launcher" && controller.loading) {
      return <WorldLoadingScreen mode="listing" error={error} onRetry={() => void controller.reloadWorlds()} onBack={onExit} />;
    }
    if (mode === "launcher") {
      return <WorldLauncher worlds={controller.worlds} busy={busy || controller.busy} error={error} onCreateWorld={() => { setPresentationError(""); setDraft(null); setMode("create"); }} onLoadWorld={(worldId) => void loadWorldForPlay(worldId)} onOpenSettings={() => { setPresentationError(""); setMode("settings"); }} onExit={onExit} />;
    }
    if (mode === "loading") {
      return <WorldLoadingScreen mode="world" busy={busy || controller.busy} error={error} onRetry={loadingWorldId ? () => void loadWorldForPlay(loadingWorldId) : undefined} onBack={() => setMode("launcher")} />;
    }
    if (mode === "settings") {
      return <WorldGameSettingsPanel onBack={() => setMode("launcher")} />;
    }
    if (mode === "create" || !world) {
      return (
        <WorldCreateFlow
          roles={worldRoles}
          initialSeed={seed}
          busy={busy}
          draft={draft}
          onRerollSeed={() => {
            const nextSeed = createWorldSeed();
            setSeed(nextSeed);
            return nextSeed;
          }}
          onPreview={previewDraft}
          onConfirm={confirmDraft}
        />
      );
    }
    if (mode === "timeline") {
      return (
        <WorldTimelineView
          worldName={world.name}
          activeOcName={controller.activeOc?.name ?? "当前 OC"}
          entries={timeline}
          perspective={perspective}
          backfillPreview={backfillPreview}
          onBack={() => setMode(timelineReturnMode)}
          onPerspectiveChange={changePerspective}
          onCopyWorld={copyWorld}
          onPreviewBackfill={previewBackfill}
          onCommitBackfill={commitBackfill}
        />
      );
    }
    if (mode === "game") {
      return (
        <WorldGameSurface
          world={world}
          busy={busy || controller.busy}
          onOpenTimeline={() => openTimeline("game")}
          onExitWorkspace={() => setMode("workspace")}
          onSubmitAction={controller.submitAction}
          onAdvance={controller.advance}
          onResolveBarrier={controller.resolveBarrier}
          onRedrawShot={controller.redrawShot}
          onPause={controller.pausePresentation}
          onResume={controller.resumePresentation}
          onCheckpoint={controller.checkpointPresentation}
          synthesizeVoice={client.synthesizeVoice}
        />
      );
    }
    return (
      <WorldWorkspace
        worlds={controller.worlds}
        world={world}
        busy={busy || controller.busy}
        error={error}
        onSelectWorld={controller.loadWorld}
        onSwitchOc={controller.switchOc}
        onCreateWorld={() => {
          setDraft(null);
          setMode("create");
        }}
        onOpenTimeline={() => openTimeline("workspace")}
        onOpenFocus={openGame}
        onSubmitAction={controller.submitAction}
        onAdvance={controller.advance}
        onResolveBarrier={controller.resolveBarrier}
        onCancel={controller.cancelRun}
        onRedrawShot={controller.redrawShot}
      />
    );
  }, [backfillPreview, busy, changePerspective, commitBackfill, confirmDraft, controller, copyWorld, draft, loadWorldForPlay, loadingWorldId, mode, onExit, openGame, openTimeline, perspective, presentationError, previewBackfill, previewDraft, seed, timeline, timelineReturnMode, world, worldRoles]);

  return { content };
}
