import { useCallback, useEffect, useMemo, useState } from "react";
import { createWorldBridgeClient, type WorldBridgeClient } from "./bridgeClient";
import { replaceWorldSummary, selectActiveOc } from "./selectors";
import type { WorldDetails, WorldSummary } from "./types";

type ControllerState = {
  worlds: WorldSummary[];
  world: WorldDetails | null;
  loading: boolean;
  busy: boolean;
  error: string;
};

const initialState: ControllerState = { worlds: [], world: null, loading: true, busy: false, error: "" };

/** Owns Story loading and input while the retained workspace remains declarative. */
export function useWorldWorkspaceController(client: WorldBridgeClient = createWorldBridgeClient()) {
  const [state, setState] = useState(initialState);

  const run = useCallback(async <T,>(operation: () => Promise<T>, apply?: (value: T) => void) => {
    setState((current) => ({ ...current, busy: true, error: "" }));
    try {
      const result = await operation();
      apply?.(result);
      return result;
    } catch (error) {
      setState((current) => ({ ...current, error: error instanceof Error ? error.message : "剧情暂时无法响应" }));
      return null;
    } finally {
      setState((current) => ({ ...current, busy: false }));
    }
  }, []);

  const applyWorld = useCallback((world: WorldDetails) => {
    setState((current) => ({ ...current, world, worlds: replaceWorldSummary(current.worlds, world) }));
  }, []);

  const loadWorld = useCallback((worldId: string) => run(() => client.getWorld(worldId), applyWorld), [applyWorld, client, run]);

  const reloadWorlds = useCallback(async () => {
    setState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const worlds = await client.listWorlds();
      setState((current) => ({ ...current, worlds, loading: false }));
    } catch (error) {
      setState((current) => ({ ...current, loading: false, error: error instanceof Error ? error.message : "无法读取剧情列表" }));
    }
  }, [client]);

  const refreshActiveStory = useCallback((storyId: string) => {
    void client.getWorld(storyId).then((world) => {
      setState((current) => current.world?.id === storyId ? { ...current, world, worlds: replaceWorldSummary(current.worlds, world) } : current);
    }).catch((error: unknown) => {
      setState((current) => current.world?.id === storyId ? { ...current, error: error instanceof Error ? error.message : "无法刷新剧情" } : current);
    });
  }, [client]);

  useEffect(() => {
    void reloadWorlds();
  }, [reloadWorlds]);

  useEffect(() => window.miraDesktop.onEvent((event) => {
    if (!new Set(["stories.beat.committed", "stories.operation.changed", "stories.failed"]).has(event.method)) return;
    const storyId = typeof event.payload.story_id === "string" ? event.payload.story_id : "";
    if (storyId) refreshActiveStory(storyId);
  }), [refreshActiveStory]);

  const catchUp = useCallback(async () => {
    if (state.world) await loadWorld(state.world.id);
  }, [loadWorld, state.world]);

  const completeDay = useCallback(async (content: string) => {
    if (!state.world || !content.trim()) return false;
    const result = await run(() => client.completeDay(state.world!.id, content.trim()));
    if (result === null) return false;
    await catchUp();
    return true;
  }, [catchUp, client, run, state.world]);

  return useMemo(() => ({ ...state, activeOc: selectActiveOc(state.world), reloadWorlds, loadWorld, completeDay, catchUp }), [catchUp, completeDay, loadWorld, reloadWorlds, state]);
}
