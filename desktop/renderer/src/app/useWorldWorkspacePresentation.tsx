import { useCallback, useMemo, useState } from "react";
import { toFileUrl } from "../shared/format";
import type { RoleRecord } from "../shared/types";
import {
  GalgameFocusMode,
  WorldCreateFlow,
  WorldTimelineView,
  WorldWorkspace,
  type BackfillPreview,
  type NativeIdentityDraft,
  type WorldCreationInput,
} from "../world";
import type { WorldBridgeClient } from "../world/bridgeClient";
import type { useWorldWorkspaceController } from "../world/useWorldWorkspaceController";

type WorldPresentationMode = "workspace" | "create" | "timeline" | "focus";

type UseWorldWorkspacePresentationArgs = {
  roles: RoleRecord[];
  client: WorldBridgeClient;
  controller: ReturnType<typeof useWorldWorkspaceController>;
};

function createWorldSeed(): string {
  return globalThis.crypto?.randomUUID?.() ?? `seed-${Date.now().toString(36)}`;
}

/** Coordinates world-only presentation modes around the persistent workspace controller. */
export function useWorldWorkspacePresentation({ roles, client, controller }: UseWorldWorkspacePresentationArgs) {
  const [mode, setMode] = useState<WorldPresentationMode>("workspace");
  const [seed, setSeed] = useState(createWorldSeed);
  const [draft, setDraft] = useState<Awaited<ReturnType<WorldBridgeClient["previewDraft"]>> | null>(null);
  const [timeline, setTimeline] = useState<Awaited<ReturnType<WorldBridgeClient["getTimeline"]>>>([]);
  const [perspective, setPerspective] = useState<"known" | "omniscient">("known");
  const [backfillPreview, setBackfillPreview] = useState<BackfillPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [presentationError, setPresentationError] = useState("");

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

  const openTimeline = useCallback(() => {
    if (!world) return;
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

  const confirmDraft = useCallback((draftId: string, identities: NativeIdentityDraft[]) => {
    void runPresentation(
      () => client.confirmDraft(draftId, identities),
      async (createdWorld) => {
        await controller.reloadWorlds();
        await controller.loadWorld(createdWorld.id);
        setDraft(null);
        setMode("workspace");
      },
    );
  }, [client, controller, runPresentation]);

  const copyWorld = useCallback((anchorId: string) => {
    if (!world) return;
    void runPresentation(
      () => client.copyWorld(world.id, anchorId),
      async (copiedWorld) => {
        await controller.reloadWorlds();
        await controller.loadWorld(copiedWorld.id);
        setMode("workspace");
      },
    );
  }, [client, controller, runPresentation, world]);

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
        await controller.loadWorld(updatedWorld.id);
        setBackfillPreview(null);
        setMode("workspace");
      },
    );
  }, [client, controller, runPresentation, world]);

  const openFocus = useCallback(() => {
    if (!world?.scene.beats.length) {
      setPresentationError("当前场景尚无可播放的剧情。");
      return;
    }
    setMode("focus");
  }, [world]);

  const content = useMemo(() => {
    const error = presentationError || controller.error;
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
          onBack={() => setMode("workspace")}
          onPerspectiveChange={changePerspective}
          onCopyWorld={copyWorld}
          onPreviewBackfill={previewBackfill}
          onCommitBackfill={commitBackfill}
        />
      );
    }
    if (mode === "focus") {
      const beat = [...world.scene.beats].reverse().find((item) => item.isCritical) ?? world.scene.beats.at(-1);
      return beat ? <GalgameFocusMode worldName={world.name} beat={beat} onExit={() => setMode("workspace")} onRedrawShot={controller.redrawShot} /> : null;
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
        onOpenTimeline={openTimeline}
        onOpenFocus={openFocus}
        onSubmitAction={controller.submitAction}
        onAdvance={controller.advance}
        onResolveBarrier={controller.resolveBarrier}
        onCancel={controller.cancelRun}
        onRedrawShot={controller.redrawShot}
      />
    );
  }, [backfillPreview, busy, changePerspective, commitBackfill, confirmDraft, controller, copyWorld, draft, mode, openFocus, openTimeline, perspective, presentationError, previewBackfill, previewDraft, seed, timeline, world, worldRoles]);

  return { content };
}
