/// <reference types="node" />
import assert from "node:assert/strict";
import { test } from "node:test";
import type { StoryDetails } from "../../../../../plugins/story/ui/types";
import { createStoryBridgeClient } from "../../../../../plugins/story/ui/storyBridgeClient";
import { createDemoStoryHost } from "./demoStoryHost";
import { storyChapters } from "./demoStoryChapters";

function storage() {
  const values = new Map<string, string>();
  return { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); }, removeItem: (key: string) => { values.delete(key); } };
}

test("the actual Story client creates, records free input, continues and restores a demo", async () => {
  const saved = storage();
  const host = createDemoStoryHost(saved, async () => undefined);
  const client = createStoryBridgeClient(host.client);
  const events: string[] = [];
  host.services.onEvent((event) => events.push(event.method));
  const story = await client.createStory({ title: "自己的标题", background: "自己的设定", storyDate: "2026-10-01", timeBand: "夜晚", roleId: "showcase-shiori", playerProfile: { displayName: "旅人", appearance: "外套", identity: "客人" } }, "test-create");
  assert.equal(story.title, "自己的标题");
  assert.equal(story.background, "自己的设定");
  assert.equal(story.currentTimeBand, "夜晚");
  const advanced = await client.submitInput(story.id, "我把车票拿起来看看。");
  assert.equal(advanced.turns.at(-1)?.input, "我把车票拿起来看看。");
  assert.equal(advanced.revision, story.revision + 1);
  assert.equal(advanced.beats.length, story.beats.length + storyChapters[1].beats.length);
  assert.ok(events.includes("plugin.story.operation.changed"));
  assert.ok(events.includes("plugin.story.beat.committed"));
  await client.continueStory(story.id);
  await client.continueStory(story.id);
  assert.equal((await client.listCgGallery()).find((entry) => entry.storyId === story.id)?.items.length, 2);
  const reopened = createStoryBridgeClient(createDemoStoryHost(saved, async () => undefined).client);
  const restored = await reopened.getStory(story.id);
  assert.equal(restored.turns.length, 4);
  assert.equal(restored.turns[1].input, "我把车票拿起来看看。");
  assert.equal(restored.revision, 4);
  for (let index = restored.turns.length; index < 12; index += 1) await reopened.continueStory(story.id);
  assert.equal((await reopened.listCgGallery()).find((entry) => entry.storyId === story.id)?.items.length, 5);
  await assert.rejects(reopened.continueStory(story.id), /这一段故事已读完/);
});

test("concurrent or stale Story mutations cannot duplicate a sample page", async () => {
  let release: () => void = () => undefined;
  const host = createDemoStoryHost(storage(), () => new Promise<void>((resolve) => { release = resolve; }));
  const client = createStoryBridgeClient(host.client);
  const story = await client.getStory("demo-bookshop");
  const pending = client.submitInput(story.id, "你好");
  await assert.rejects(client.continueStory(story.id), /等当前操作/);
  release();
  await pending;
  await assert.rejects(host.client.call("input", { story_id: story.id, expected_revision: 1, input: "stale" }), /剧情已更新/);
});

test("reset and disposal invalidate pending writes before they can resurrect old stories", async () => {
  for (const mode of ["reset", "dispose"]) {
    const saved = storage();
    let release: () => void = () => undefined;
    const host = createDemoStoryHost(saved, () => new Promise<void>((resolve) => { release = resolve; }));
    const pending = host.client.call("input", { story_id: "demo-bookshop", expected_revision: 1, input: "旧输入" });
    if (mode === "reset") host.reset(); else await host.client.dispose();
    release();
    await assert.rejects(pending, /重置或关闭/);
    const restored = await createDemoStoryHost(saved).client.call<{ story: StoryDetails }>("get", { story_id: "demo-bookshop" });
    assert.equal(restored.story.turns.length, 1);
  }
});
