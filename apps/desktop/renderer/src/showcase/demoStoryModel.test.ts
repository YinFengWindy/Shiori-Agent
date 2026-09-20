/// <reference types="node" />
import assert from "node:assert/strict";
import { test } from "node:test";
import { appendDemoStoryTurn, createDemoStory, demoStorySummary } from "./demoStoryModel";

test("sample turns preserve chronological beats and the original Story wire contracts", () => {
  const opening = createDemoStory();
  const next = appendDemoStoryTurn(opening, "先看车票", "player");
  assert.equal(opening.turns.length, 1);
  assert.deepEqual(next.beats.map((beat) => beat.sequence), [1, 2, 3, 4, 5, 6]);
  assert.equal(next.segment.operation, "awaiting_player");
  assert.equal(next.turns[1].committedBeatIds.length, 3);
  assert.equal(next.backgroundResource?.visualType, "character");
  assert.equal(demoStorySummary(next).current_scene.name, "街角旧书店");
});

test("invalid creation fields never become a partially valid Story read model", () => {
  assert.throws(() => createDemoStory({ time_band: "某一天" }), /有效的故事时段/);
  assert.throws(() => createDemoStory({ player_profile: null }), /完整的玩家资料/);
});
