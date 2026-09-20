/// <reference types="node" />
import assert from "node:assert/strict";
import { test } from "node:test";
import { demoStoriesStorageKey, persistDemoStories, restoreDemoStories } from "./demoStoryPersistence";
import { appendDemoStoryTurn, createDemoStory } from "./demoStoryModel";
import { demoBackdrop } from "./demoContent";

test("malformed, old full-read-model and forged fixture storage are rejected", () => {
  for (const raw of ["{", "null", JSON.stringify([{ id: "demo-a", beats: [null], roleSnapshot: null, currentScene: {} }]), JSON.stringify([{ id: "demo-a", turns: [{ kind: "evil", input: "x" }] }])]) {
    const stories = restoreDemoStories({ getItem: () => raw, setItem: () => undefined, removeItem: () => undefined });
    assert.equal(stories[0].id, "demo-bookshop");
    assert.equal(stories[0].turns.length, 1);
  }
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
