import { useCallback, useEffect, useMemo, useState } from "react";
import { createWorldBridgeClient, type WorldBridgeClient } from "./bridgeClient";
import { mergeCommittedBeats, selectActiveOc, selectWorld } from "./selectors";
import type { DecisionBarrier, SceneShot, WorldDetails, WorldSummary } from "./types";

type ControllerState = {
  worlds: WorldSummary[];
  world: WorldDetails | null;
  loading: boolean;
  busy: boolean;
  error: string;
  cursor: string;
};

const initialState: ControllerState = {
  worlds: [],
  world: null,
  loading: true,
  busy: false,
  error: "",
  cursor: "",
};

/** Owns world loading and all workspace commands while views remain declarative. */
export function useWorldWorkspaceController(client: WorldBridgeClient = createWorldBridgeClient()) {
  const [state, setState] = useState(initialState);

  const run = useCallback(async <T,>(operation: () => Promise<T>, apply?: (value: T) => void) => {
    setState((current) => ({ ...current, busy: true, error: "" }));
    try {
      const result = await operation();
      apply?.(result);
      return result;
    } catch (error) {
      setState((current) => ({ ...current, error: error instanceof Error ? error.message : "世界暂时无法响应" }));
      return null;
    } finally {
      setState((current) => ({ ...current, busy: false }));
    }
  }, []);

  const loadWorld = useCallback(async (worldId: string) => {
    await run(() => client.getWorld(worldId), (world) => {
      setState((current) => ({ ...current, world }));
    });
  }, [client, run]);

  const reloadWorlds = useCallback(async () => {
    setState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const worlds = await client.listWorlds();
      const selected = selectWorld(worlds, state.world?.id ?? "");
      const world = selected ? await client.getWorld(selected.id) : null;
      setState((current) => ({ ...current, worlds, world, loading: false }));
    } catch (error) {
      setState((current) => ({
        ...current,
        loading: false,
        error: error instanceof Error ? error.message : "无法读取世界",
      }));
    }
  }, [client, state.world?.id]);

  useEffect(() => {
    void reloadWorlds();
  }, []); // The client is stable for the lifetime of the workspace.

  const catchUp = useCallback(async () => {
    if (!state.world) return;
    const update = await run(() => client.catchUp(state.world!.id, state.cursor));
    if (!update) return;
    setState((current) => {
      const baseWorld = update.world ?? current.world;
      if (!baseWorld) return current;
      return {
        ...current,
        cursor: update.cursor,
        world: {
          ...baseWorld,
          scene: {
            ...baseWorld.scene,
            beats: mergeCommittedBeats(baseWorld.scene.beats, update.beats),
          },
        },
      };
    });
  }, [client, run, state.cursor, state.world]);

  const switchOc = useCallback(async (ocId: string) => {
    if (!state.world || state.world.activeOcId === ocId) return;
    await run(() => client.switchOc(state.world!.id, ocId), (world) => setState((current) => ({ ...current, world })));
  }, [client, run, state.world]);

  const submitAction = useCallback(async (content: string) => {
    if (!state.world || !content.trim()) return false;
    const result = await run(() => client.submitAction(state.world!.id, content.trim()));
    if (result === null) return false;
    await catchUp();
    return true;
  }, [catchUp, client, run, state.world]);

  const advance = useCallback(async () => {
    if (!state.world) return;
    const result = await run(() => client.advance(state.world!.id));
    if (result !== null) await catchUp();
  }, [catchUp, client, run, state.world]);

  const resolveBarrier = useCallback(async (barrier: DecisionBarrier, choiceId: string) => {
    if (!state.world) return;
    await run(
      () => client.resolveBarrier(state.world!.id, barrier, choiceId),
      (world) => setState((current) => ({ ...current, world })),
    );
  }, [client, run, state.world]);

  const cancelRun = useCallback(async () => {
    if (!state.world) return;
    await run(() => client.cancelRun(state.world!.id), (world) => setState((current) => ({ ...current, world })));
  }, [client, run, state.world]);

  const redrawShot = useCallback(async (shotId: string) => {
    if (!state.world) return;
    await run(() => client.redrawShot(state.world!.id, shotId), (shot: SceneShot) => {
      setState((current) => current.world ? ({
        ...current,
        world: {
          ...current.world,
          scene: {
            ...current.world.scene,
            beats: current.world.scene.beats.map((beat) => beat.shot?.id === shotId ? { ...beat, shot } : beat),
          },
        },
      }) : current);
    });
  }, [client, run, state.world]);

  return useMemo(() => ({
    ...state,
    activeOc: selectActiveOc(state.world),
    reloadWorlds,
    loadWorld,
    switchOc,
    submitAction,
    advance,
    resolveBarrier,
    cancelRun,
    catchUp,
    redrawShot,
  }), [advance, cancelRun, catchUp, loadWorld, redrawShot, reloadWorlds, resolveBarrier, state, submitAction, switchOc]);
}
