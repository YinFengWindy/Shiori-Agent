import type { BridgeEvent } from "../../../src/bridge/shared";
import type { PluginRpcClient } from "../plugins/pluginBridgeClient";
import type { PluginHostServices } from "../plugins/pluginHostServices";
import type { StoryDetails } from "../../../../../plugins/story/ui/types";
import { demoRole } from "./demoContent";
import { storyChapters } from "./demoStoryChapters";
import { appendDemoStoryTurn, createDemoStory, demoStorySummary } from "./demoStoryModel";
import type { DemoStorage } from "./demoStorage";
import { demoStoriesStorageKey, persistDemoStories, restoreDemoStories } from "./demoStoryPersistence";

const sleep = () => new Promise<void>((resolve) => setTimeout(resolve, 600));

/** Fixture-backed host for the unchanged Story page; implements no desktop or AI transport. */
export function createDemoStoryHost(storage: DemoStorage, wait = sleep) {
  const stories = new Map<string, StoryDetails>(restoreDemoStories(storage).map((story) => [story.id, story]));
  const listeners = new Set<(event: BridgeEvent) => void>();
  let busy = false;
  let lifetime = 0;
  let disposed = false;
  const emit = (story: StoryDetails, name: string) => {
    const event: BridgeEvent = { id: story.id, type: "event", method: `plugin.story.${name}`, payload: { story_id: story.id, story_revision: story.revision } };
    for (const listener of listeners) listener(event);
  };
  const requireStory = (payload: Record<string, unknown>) => {
    const story = stories.get(String(payload.story_id));
    if (!story) throw new Error("找不到这段剧情。");
    return story;
  };
  const unsupported = async (): Promise<never> => { throw new Error("此能力需下载 Shiori 桌面端使用。"); };
  const services: PluginHostServices = {
    onEvent: (listener) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    listRoles: async () => [demoRole], pickImages: unsupported, pickFiles: unsupported,
  };

  async function call(name: string, payload: Record<string, unknown>) {
    if (disposed) throw new Error("页面已关闭。");
    if (name === "list") return { stories: [...stories.values()].map(demoStorySummary) };
    if (name === "get") return { story: requireStory(payload) };
    if (name === "cg.list") return { stories: [...stories.values()].map((story) => ({ story_id: story.id, title: story.title, status: story.status, created_at: story.turns[0]?.createdAt ?? "", items: story.cgGallery })) };
    if (busy) throw new Error("请等当前操作完成。");
    if (!["create", "input", "continue", "cg.retry", "cg.regenerate"].includes(name)) return unsupported();
    let story = name === "create" ? createDemoStory(payload) : requireStory(payload);
    if (name === "create") {
      if (stories.has(story.id)) return { story: stories.get(story.id) };
      if (stories.size >= 12) throw new Error("最多保留 12 段故事，可在网页顶部选择「重新开始」。");
    }
    if (name === "input" || name === "continue") {
      if (payload.expected_revision !== story.revision) throw new Error("剧情已更新，请重新打开这段故事。");
      if (story.turns.length >= storyChapters.length) throw new Error("这一段故事已读完。可返回剧情记录重读，或回主菜单新建故事。");
      if (name === "input" && !String(payload.input || "").trim()) throw new Error("请输入一句台词或行动。");
    }
    busy = true;
    const token = lifetime;
    const previous = stories.get(story.id);
    stories.set(story.id, { ...story, segment: { ...story.segment, operation: "generating" } });
    emit(story, "operation.changed");
    try {
      await wait();
      if (lifetime !== token) throw new Error("页面已重置或关闭。");
      if (name === "input" || name === "continue") story = appendDemoStoryTurn(story, String(payload.input || ""), name === "input" ? "player" : "continue");
      // Regeneration is an explicitly labelled replay of the same preset artwork.
      if (name.startsWith("cg.")) story = { ...story, cgGallery: story.cgGallery.map((resource) => resource.id === payload.resource_id ? { ...resource, updatedAt: new Date().toISOString() } : resource) };
      stories.set(story.id, story);
      persistDemoStories(storage, stories.values());
      emit(story, "beat.committed");
      emit(story, "resource.changed");
      return { story };
    } catch (error) {
      if (lifetime === token) {
        if (previous) stories.set(story.id, previous);
        else stories.delete(story.id);
      }
      throw error;
    } finally { if (lifetime === token) { busy = false; emit(story, "operation.changed"); } }
  }
  const client: PluginRpcClient = {
    call: async <T,>(name: string, payload: Record<string, unknown> = {}) => structuredClone(await call(name, payload)) as T,
    events: { on: async (name, listener) => services.onEvent((event) => { if (event.method === `plugin.story.${name}`) listener(event.payload, event); }) },
    dependency: async () => null, background: { call: unsupported }, handle: unsupported,
    dispose: async () => { disposed = true; lifetime += 1; listeners.clear(); },
  };
  return { client, services, reset: () => {
    lifetime += 1;
    busy = false;
    stories.clear();
    const initial = createDemoStory();
    stories.set(initial.id, initial);
    storage.removeItem(demoStoriesStorageKey);
  } };
}
