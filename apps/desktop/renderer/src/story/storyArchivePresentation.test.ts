/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { buildStoryArchiveDays } from "./storyArchivePresentation";
import { createStoryBeat, createStoryDetails } from "./testFixtures";

describe("buildStoryArchiveDays", () => {
  it("uses the in-story effective time instead of the system recording time", () => {
    const beat = createStoryBeat({ storyDate: "2026-08-01", recordedAt: "2026-08-04T21:30:00+08:00" });
    const story = createStoryDetails({ beats: [beat] });

    const days = buildStoryArchiveDays(story);

    assert.deepEqual(days.map((day) => day.label), ["2026年8月1日"]);
  });

  it("groups dates and time periods while distinguishing narration, dialogue, and player entries", () => {
    const story = createStoryDetails({
      beats: [
        createStoryBeat({ id: "narration", sequence: 1, kind: "narration", speaker: null, timeBand: "上午", text: "雨停了。", recordedAt: "2026-08-02T10:00:00+08:00" }),
        createStoryBeat({ id: "dialogue", sequence: 2, kind: "dialogue", speaker: "哈风", timeBand: "上午", text: "你来了。", recordedAt: "2026-08-02T10:02:00+08:00" }),
        createStoryBeat({ id: "night", sequence: 3, kind: "dialogue", speaker: "哈风", storyDate: "2026-08-03", timeBand: "夜晚", text: "灯亮了。", recordedAt: "2026-08-03T20:00:00+08:00" }),
      ],
      turns: [{ id: "turn-player", kind: "player", input: "我走近灯火。", status: "committed", attemptId: null, committedBeatIds: ["dialogue"], error: null, createdAt: "2026-08-02T10:01:00+08:00", updatedAt: "2026-08-02T10:02:00+08:00" }],
    });

    const days = buildStoryArchiveDays(story);

    assert.deepEqual(days.map((day) => day.label), ["2026年8月2日", "2026年8月3日"]);
    assert.deepEqual(days[0]?.periods.map((period) => period.timeBand), ["上午"]);
    assert.deepEqual(days[0]?.periods[0]?.entries.map(({ kind, label, text }) => ({ kind, label, text })), [
      { kind: "narration", label: "旁白", text: "雨停了。" },
      { kind: "player", label: "玩家", text: "我走近灯火。" },
      { kind: "dialogue", label: "哈风", text: "你来了。" },
    ]);
    assert.deepEqual(days[1]?.periods.map((period) => period.timeBand), ["夜晚"]);
  });

  it("splits mixed narrative and quoted dialogue into separate archive entries", () => {
    const story = createStoryDetails({
      beats: [createStoryBeat({
        kind: "dialogue",
        speaker: "吟风",
        text: "她抬眼看向你，耳尖悄悄染上一抹粉：\"哼……算你有眼光。\"",
      })],
    });

    const entries = buildStoryArchiveDays(story)[0]?.periods[0]?.entries ?? [];

    assert.deepEqual(entries.map(({ kind, label, text }) => ({ kind, label, text })), [
      { kind: "narration", label: "旁白", text: "她抬眼看向你，耳尖悄悄染上一抹粉：" },
      { kind: "dialogue", label: "吟风", text: "\"哼……算你有眼光。\"" },
    ]);
  });

  it("does not show uncommitted or input-less turns", () => {
    const story = createStoryDetails({
      turns: [
        { id: "opening", kind: "opening", input: "", status: "committed", attemptId: null, committedBeatIds: ["beat-1"], error: null, createdAt: "2026-08-02T09:00:00+08:00", updatedAt: "2026-08-02T09:00:00+08:00" },
        { id: "pending", kind: "player", input: "还没提交", status: "pending", attemptId: null, committedBeatIds: [], error: null, createdAt: "2026-08-02T09:01:00+08:00", updatedAt: "2026-08-02T09:01:00+08:00" },
      ],
    });

    const entries = buildStoryArchiveDays(story)[0]?.periods[0]?.entries ?? [];

    assert.deepEqual(entries.map((entry) => entry.id), ["beat:beat-1"]);
  });
});
