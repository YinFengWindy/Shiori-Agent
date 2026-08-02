import { useCallback, useEffect, useState } from "react";
import type { StoryBridgeClient } from "./bridgeClient";
import type { StoryCreationInput, StoryDetails, StorySummary } from "./types";

type StoryControllerState = {
  stories: StorySummary[];
  story: StoryDetails | null;
  loading: boolean;
  busy: boolean;
  error: string;
};

const initialState: StoryControllerState = {
  stories: [],
  story: null,
  loading: true,
  busy: false,
  error: "",
};

/** Owns Story loading, command submission, and committed-event refreshes. */
export function useStoryController(client: StoryBridgeClient) {
  const [state, setState] = useState(initialState);

  const reloadLibrary = useCallback(async () => {
    try {
      const stories = await client.listStories();
      setState((current) => ({ ...current, stories, loading: false }));
    } catch (error) {
      setState((current) => ({
        ...current,
        loading: false,
        error: error instanceof Error ? error.message : "无法读取 Story",
      }));
    }
  }, [client]);

  const loadStory = useCallback(async (storyId: string) => {
    try {
      const story = await client.getStory(storyId);
      setState((current) => ({ ...current, story, error: "" }));
    } catch (error) {
      setState((current) => ({
        ...current,
        error: error instanceof Error ? error.message : "无法读取 Story",
      }));
    }
  }, [client]);

  const run = useCallback(async (operation: () => Promise<void>) => {
    setState((current) => ({ ...current, busy: true, error: "" }));
    try {
      await operation();
    } catch (error) {
      setState((current) => ({
        ...current,
        error: error instanceof Error ? error.message : "Story 暂时无法响应",
      }));
    } finally {
      setState((current) => ({ ...current, busy: false }));
    }
  }, []);

  const createStory = useCallback(async (input: StoryCreationInput): Promise<boolean> => {
    setState((current) => ({ ...current, busy: true, error: "" }));
    try {
      const story = await client.createStory(input);
      const stories = await client.listStories();
      setState((current) => ({ ...current, stories, story }));
      return true;
    } catch (error) {
      setState((current) => ({
        ...current,
        error: error instanceof Error ? error.message : "无法创建 Story",
      }));
      return false;
    } finally {
      setState((current) => ({ ...current, busy: false }));
    }
  }, [client]);

  const submitInput = useCallback(async (input: string) => {
    const story = state.story;
    if (!story) return;
    await run(() => client.submitInput(story.id, input, story.revision));
  }, [client, run, state.story]);

  const continueStory = useCallback(async () => {
    const story = state.story;
    if (!story) return;
    await run(() => client.continueStory(story.id, story.revision));
  }, [client, run, state.story]);

  const closeStory = useCallback(() => {
    setState((current) => (current.story ? { ...current, story: null, error: "" } : current));
  }, []);

  useEffect(() => {
    void reloadLibrary();
  }, [reloadLibrary]);

  useEffect(() => {
    const activeStoryId = state.story?.id ?? "";
    const off = window.miraDesktop.onEvent((event) => {
      if (!event.method.startsWith("stories.")) return;
      const storyId = String(event.payload.story_id ?? "");
      if (!storyId) return;
      if (storyId === activeStoryId) void loadStory(storyId);
      void reloadLibrary();
    });
    return off;
  }, [loadStory, reloadLibrary, state.story?.id]);

  return { ...state, createStory, loadStory, reloadLibrary, submitInput, continueStory, closeStory };
}
