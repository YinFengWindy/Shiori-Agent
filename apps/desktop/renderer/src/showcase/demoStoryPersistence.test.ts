/// <reference types="node" />
import assert from "node:assert/strict";
import { test } from "node:test";
import { demoStoriesStorageKey, persistDemoStories, restoreDemoStories } from "./demoStoryPersistence";
import { appendDemoStoryTurn, createDemoStory } from "./demoStoryModel";
import { demoBackdrop } from "./demoContent";
import { selectActiveStoryVisualResource } from "../../../../../plugins/story/ui/selectors";
import { storyArtwork } from "./demoAssets";

test("malformed, old full-read-model and forged fixture storage are rejected", () => {
  for (const raw of ["{", "null", JSON.stringify([{ id: "demo-a", beats: [null], roleSnapshot: null, currentScene: {} }]), JSON.stringify([{ id: "demo-a", turns: [{ kind: "evil", input: "x" }] }])]) {
    const stories = restoreDemoStories({ getItem: () => raw, setItem: () => undefined, removeItem: () => undefined });
    assert.equal(stories[0].id, "demo-bookshop");
    assert.equal(stories[0].turns.length, 1);
  }
});

test("full-story restoration preserves opening time, later beats, scene and unlocked CG order", () => {
  let raw = "";
  const storage = { getItem: () => raw, setItem: (_key: string, value: string) => { raw = value; }, removeItem: () => undefined };
  let story = createDemoStory();
  for (let index = 1; index < 12; index += 1) story = appendDemoStoryTurn(story, `第 ${index} 次回应`, "player");
  assert.equal(story.beats[0].timeBand, "下午");
  assert.equal(story.currentTimeBand, "夜晚");
  persistDemoStories(storage, [story]);
  const restored = restoreDemoStories(storage)[0];
  assert.deepEqual(restored.beats.map((beat) => beat.timeBand), story.beats.map((beat) => beat.timeBand));
  assert.deepEqual(restored.turns.map((turn) => turn.input), story.turns.map((turn) => turn.input));
  assert.deepEqual(restored.cgGallery.map((resource) => resource.path), story.cgGallery.map((resource) => resource.path));
  assert.equal(selectActiveStoryVisualResource(restored)?.path, storyArtwork.fireworks);
  assert.equal(restored.currentScene.name, "烟花下的河岸");
});

test("previous saves without an opening-time field still reopen without losing input", () => {
  const raw = JSON.stringify([{ id: "demo-bookshop", title: "雨停之前", background: "旧书店", playerProfile: { display_name: "旅人", appearance: "外套", identity: "访客" }, currentStoryDate: "2026-09-20", currentTimeBand: "下午", turns: [{ kind: "opening", input: "" }, { kind: "player", input: "老存档里的回应" }] }]);
  const restored = restoreDemoStories({ getItem: () => raw, setItem: () => undefined, removeItem: () => undefined })[0];
  assert.equal(restored.turns[1].input, "老存档里的回应");
  assert.equal(restored.beats[0].timeBand, "下午");
  assert.equal(restored.roleSnapshot.name, "吟风");
});

test("storage restores actual turn inputs without trusting serialized assets or beat content", () => {
  let raw = "";
  const storage = { getItem: () => raw, setItem: (key: string, value: string) => { assert.equal(key, demoStoriesStorageKey); raw = value; }, removeItem: () => undefined };
  const story = appendDemoStoryTurn(createDemoStory(), "访客输入", "player");
  story.beats[0].text = "不可持久化的替换文本";
  persistDemoStories(storage, [story]);
  assert.doesNotMatch(raw, /不可持久化|"path"|"beats"/);
  const restored = restoreDemoStories(storage)[0];
  assert.equal(restored.turns[1].input, "访客输入");
  assert.equal(restored.backgroundResource?.path, demoBackdrop);
  assert.notEqual(restored.beats[0].text, "不可持久化的替换文本");
});
