import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createStoryBridgeClient, type StoryBridgeClient } from "./storyBridgeClient";
import { replaceStorySummary } from "./selectors";
import { waitForMinimumStoryLoading } from "./storyLoadingPresentation";
import type { StoryDetails, StorySummary } from "./types";

type ControllerState = {
  stories: StorySummary[];
  story: StoryDetails | null;
  loading: boolean;
  busy: boolean;
  error: string;
};

const initialState: ControllerState = { stories: [], story: null, loading: true, busy: false, error: "" };
const storyResourcePollMs = 350;
const storyResourcePollLimit = 240;

/** Owns Story list, read-model refresh, and player input state. */
export function useStoryController(client: StoryBridgeClient = createStoryBridgeClient()) {
  const [state, setState] = useState(initialState);
  const initialListLoadRef = useRef(true);

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

  const applyStory = useCallback((story: StoryDetails) => {
    setState((current) => ({ ...current, story, stories: replaceStorySummary(current.stories, story) }));
  }, []);

  const loadStory = useCallback((storyId: string) => run(() => client.getStory(storyId), applyStory), [applyStory, client, run]);

  const waitForStoryReady = useCallback(async (storyId: string, initialStory: StoryDetails) => {
    let current = initialStory;
    for (let attempt = 0; attempt < storyResourcePollLimit; attempt += 1) {
      if (current.backgroundResource?.status !== "generating") return current;
      await new Promise<void>((resolve) => window.setTimeout(resolve, storyResourcePollMs));
      const next = await client.getStory(storyId);
      applyStory(next);
      current = next;
    }
    return current;
  }, [applyStory, client]);

  const reloadStories = useCallback(async () => {
    const isInitialListLoad = initialListLoadRef.current;
    const startedAt = Date.now();
    setState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const stories = await client.listStories();
      if (isInitialListLoad) await waitForMinimumStoryLoading(startedAt);
      setState((current) => ({ ...current, stories, loading: false }));
    } catch (error) {
      setState((current) => ({ ...current, loading: false, error: error instanceof Error ? error.message : "无法读取剧情列表" }));
    } finally {
      if (isInitialListLoad) initialListLoadRef.current = false;
    }
  }, [client]);

  const refreshStory = useCallback((storyId: string) => {
    void client.getStory(storyId).then((story) => {
      setState((current) => current.story?.id === storyId ? { ...current, story, stories: replaceStorySummary(current.stories, story) } : current);
    }).catch((error: unknown) => {
      setState((current) => current.story?.id === storyId ? { ...current, error: error instanceof Error ? error.message : "无法刷新剧情" } : current);
    });
  }, [client]);

  useEffect(() => {
    void reloadStories();
  }, [reloadStories]);

  useEffect(() => window.miraDesktop.onEvent((event) => {
    if (!new Set(["stories.beat.committed", "stories.operation.changed", "stories.resource.changed", "stories.failed"]).has(event.method)) return;
    const storyId = typeof event.payload.story_id === "string" ? event.payload.story_id : "";
    if (storyId) refreshStory(storyId);
  }), [refreshStory]);

  const submitInput = useCallback(async (input: string) => {
    if (!state.story || !input.trim()) return false;
    const story = await run(() => client.submitInput(state.story!.id, input.trim()), applyStory);
    return story !== null;
  }, [applyStory, client, run, state.story]);

  const continueStory = useCallback(async () => {
    if (!state.story) return false;
    const story = await run(() => client.continueStory(state.story!.id), applyStory);
    return story !== null;
  }, [applyStory, client, run, state.story]);

  return useMemo(() => ({
    ...state,
    reloadStories,
    loadStory,
    waitForStoryReady,
    submitInput,
    continueStory,
  }), [continueStory, loadStory, reloadStories, state, submitInput, waitForStoryReady]);
}
