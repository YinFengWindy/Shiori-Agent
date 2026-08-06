/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { formatStoryDate, getStoryCurrentTimeBand, normalizeStoryTimeBand } from "./storyTime";
import { createStoryBeat, createStoryDetails } from "./testFixtures";

describe("normalizeStoryTimeBand", () => {
  it("formats the persisted Story date without using the system date", () => {
    assert.equal(formatStoryDate("2026-08-01"), "2026年8月1日");
    assert.equal(formatStoryDate("2026-08-01T10:00:00+08:00"), "日期未知");
  });

  it("accepts only the five player-facing periods", () => {
    assert.equal(normalizeStoryTimeBand("上午"), "上午");
    assert.equal(normalizeStoryTimeBand("2026-08-02T10:00"), "时间未知");
  });

  it("uses the latest beat before the segment period", () => {
    const story = createStoryDetails({
      segment: { ...createStoryDetails().segment, timeBand: "上午" },
      beats: [createStoryBeat({ timeBand: "夜晚" })],
    });
    assert.equal(getStoryCurrentTimeBand(story), "夜晚");
  });
});
