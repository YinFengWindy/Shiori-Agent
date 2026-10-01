import { describeStoryFailure } from "./storyFailure";
import { usePluginHostServices } from "@shiori/sdk";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type StoryBridgeClient } from "./storyBridgeClient";
import { replaceStorySummary } from "./selectors";
import { waitForMinimumStoryLoadingStage, waitForStoryLoadingCompletion } from "./storyLoadingPresentation";
import type { StoryListingLoadingPhase } from "./storyLoadingPresentation";
import type { StoryDetails, StorySummary } from "./types";

type ControllerState = {
  stories: StorySummary[];
  story: StoryDetails | null;
  loading: boolean;
  loadingPhase: StoryListingLoadingPhase;
  busy: boolean;
  error: string;
  errorDetail?: string;
};

const initialState: ControllerState = { stories: [], story: null, loading: true, loadingPhase: "reading-list", busy: false, error: "", errorDetail: undefined };
const storyResourcePollMs = 350;
const storyResourcePollLimit = 240;

/** Owns Story list, read-model refresh, and player input state. */
export function useStoryController(client: StoryBridgeClient) {
  const host = usePluginHostServices();
  const [state, setState] = useState(initialState);
  const refreshSequenceRef = useRef(new Map<string, number>());

  const run = useCallback(async <T,>(operation: () => Promise<T>, apply?: (value: T) => void, options?: { rethrow?: boolean }) => {
    setState((current) => ({ ...current, busy: true, error: "", errorDetail: undefined }));
    try {
      const result = await operation();
      apply?.(result);
      return result;
    } catch (error) {
      if (options?.rethrow) throw error;
      setState((current) => ({ ...current, ...describeStoryFailure(error, "剧情操作未完成，请重试") }));
      return null;
    } finally {
      setState((current) => ({ ...current, busy: false }));
    }
  }, []);

  const applyStory = useCallback((story: StoryDetails) => {
    setState((current) => {
      if (current.story?.id === story.id && story.revision < current.story.revision) return current;
      return { ...current, story, stories: replaceStorySummary(current.stories, story) };
    });
  }, []);

  const loadStory = useCallback((storyId: string) => run(() => client.getStory(storyId), applyStory, { rethrow: true }), [applyStory, client, run]);

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
    const startedAt = Date.now();
    setState((current) => ({ ...current, loading: true, loadingPhase: "reading-list", error: "", errorDetail: undefined }));
    try {
      const stories = await client.listStories();
      await waitForMinimumStoryLoadingStage(startedAt);
      setState((current) => ({ ...current, loadingPhase: "preparing-menu" }));
      await waitForMinimumStoryLoadingStage(Date.now());
      setState((current) => ({ ...current, stories, loadingPhase: "menu-ready" }));
      await waitForStoryLoadingCompletion();
      setState((current) => ({ ...current, stories, loading: false }));
    } catch (error) {
      setState((current) => ({ ...current, loading: true, ...describeStoryFailure(error, "剧情列表加载失败，请重试") }));
    }
  }, [client]);

  const refreshStory = useCallback((storyId: string) => {
    const sequence = (refreshSequenceRef.current.get(storyId) ?? 0) + 1;
    refreshSequenceRef.current.set(storyId, sequence);
    void client.getStory(storyId).then((story) => {
      if (refreshSequenceRef.current.get(storyId) !== sequence) return;
      applyStory(story);
    }).catch((error: unknown) => {
      if (refreshSequenceRef.current.get(storyId) !== sequence) return;
      setState((current) => current.story?.id === storyId ? { ...current, ...describeStoryFailure(error, "剧情刷新失败，请重试") } : current);
    });
  }, [applyStory, client]);

  useEffect(() => {
    void reloadStories();
  }, [reloadStories]);

  useEffect(() => host.onEvent((event) => {
    if (!new Set(["plugin.story.beat.committed", "plugin.story.operation.changed", "plugin.story.resource.changed", "plugin.story.failed"]).has(event.method)) return;
    const storyId = typeof event.payload.story_id === "string" ? event.payload.story_id : "";
    if (storyId) refreshStory(storyId);
  }), [host, refreshStory]);

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

  const regenerateCg = useCallback(async (resourceId: string) => {
    if (!state.story) return false;
    const story = await run(() => client.regenerateCg(state.story!.id, resourceId), applyStory);
    return story !== null;
  }, [applyStory, client, run, state.story]);

  return useMemo(() => ({
    ...state,
    reloadStories,
    loadStory,
    waitForStoryReady,
    submitInput,
    continueStory,
    regenerateCg,
  }), [continueStory, loadStory, regenerateCg, reloadStories, state, submitInput, waitForStoryReady]);
}
