/// <reference types="node" />
import assert from "node:assert/strict";
import { test } from "node:test";
import { appendDemoStoryTurn, createDemoStory, demoStorySummary } from "./demoStoryModel";
import { selectActiveStoryVisualResource } from "../../../../../plugins/story/ui/selectors";
import { storyArtwork } from "./demoAssets";
import { demoRole } from "./demoContent";
import { storyChapters } from "./demoStoryChapters";

test("sample turns preserve chronological beats and the original Story wire contracts", () => {
  const opening = createDemoStory();
  const next = appendDemoStoryTurn(opening, "先看车票", "player");
  assert.equal(opening.turns.length, 1);
  assert.deepEqual(next.beats.map((beat) => beat.sequence), Array.from({ length: next.beats.length }, (_, index) => index + 1));
  assert.equal(next.segment.operation, "awaiting_player");
  assert.equal(next.turns[1].committedBeatIds.length, storyChapters[1].beats.length);
  assert.equal(next.backgroundResource?.visualType, "character");
  assert.equal(demoStorySummary(next).current_scene.name, "街角旧书店");
});

test("the complete twelve-part story unlocks five CGs once and displays each current scene", () => {
  let story = createDemoStory();
  assert.equal(story.roleSnapshot.name, "吟风");
  const displayed: string[] = [];
  for (let index = 0; index < 12; index += 1) {
    if (index > 0) story = appendDemoStoryTurn(story, "继续走吧", "player");
    const visual = selectActiveStoryVisualResource(story);
    assert.ok(visual?.path, `chapter ${index + 1} must have its own scene visual`);
    assert.equal(visual.sceneKey, story.currentScene.key);
    if (displayed.at(-1) !== visual.path) displayed.push(visual.path);
    assert.ok(story.currentScene.characterIds.includes(demoRole.id));
    assert.equal(story.cgGallery.length, new Set(story.cgGallery.map((resource) => resource.path)).size);
  }
  assert.deepEqual(displayed, [storyArtwork.rain, storyArtwork.sunset, storyArtwork.desk, storyArtwork.walk, storyArtwork.fireworks]);
  assert.deepEqual(story.cgGallery.map((resource) => resource.path), displayed);
  assert.equal(story.turns.length, 12);
  assert.equal(story.currentTimeBand, "夜晚");
  assert.match(story.beats.at(-1)?.text ?? "", /小恶魔的约定/);
  assert.throws(() => appendDemoStoryTurn(story, "再来", "player"), /这一段故事已读完/);
});

test("invalid creation fields never become a partially valid Story read model", () => {
  assert.throws(() => createDemoStory({ time_band: "某一天" }), /有效的故事时段/);
  assert.throws(() => createDemoStory({ player_profile: null }), /完整的玩家资料/);
});
