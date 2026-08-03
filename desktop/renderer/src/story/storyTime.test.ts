/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { getStoryCurrentAt, getStoryTimeBand } from "./storyTime";
import { createStoryBeat, createStoryDetails } from "./testFixtures";

describe("getStoryTimeBand", () => {
  it("maps Beijing hours into five Story periods", () => {
    assert.equal(getStoryTimeBand("2026-08-02T04:59:00+08:00"), "深夜");
    assert.equal(getStoryTimeBand("2026-08-02T05:00:00+08:00"), "清晨");
    assert.equal(getStoryTimeBand("2026-08-02T09:00:00+08:00"), "上午");
    assert.equal(getStoryTimeBand("2026-08-02T12:00:00+08:00"), "下午");
    assert.equal(getStoryTimeBand("2026-08-02T18:00:00+08:00"), "夜晚");
    assert.equal(getStoryTimeBand("2026-08-02T23:00:00+08:00"), "深夜");
  });

  it("uses the current Story beat before the segment start", () => {
    const story = createStoryDetails({
      segment: { ...createStoryDetails().segment, startsAt: "2026-08-02T09:00:00+08:00" },
      beats: [createStoryBeat({ effectiveAt: "2026-08-02T14:00:00+08:00" })],
    });
    assert.equal(getStoryTimeBand(getStoryCurrentAt(story)), "下午");
  });
});
