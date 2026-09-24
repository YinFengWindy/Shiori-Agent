/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { observeMood, type MoodCueTracker } from "./moodChangeCue";

const viewedAt = Date.parse("2026-09-25T10:00:00+08:00");
const after = (seconds: number) => new Date(viewedAt + seconds * 1000).toISOString();

function run(observations: Array<{ scope: string; mood: string; updatedAt: string; now?: number }>): boolean[] {
  let tracker: MoodCueTracker | null = null;
  return observations.map((observation) => {
    const result = observeMood(tracker, { now: viewedAt, ...observation });
    tracker = result.tracker;
    return result.play;
  });
}

describe("observeMood", () => {
  it("never plays the first mood seen (initial load)", () => {
    assert.deepEqual(run([{ scope: "rin|role:rin", mood: "开心", updatedAt: after(0) }]), [false]);
  });

  it("plays a new mood stamped while the chat was in view", () => {
    assert.deepEqual(run([
      { scope: "rin|role:rin", mood: "平静", updatedAt: after(-60) },
      { scope: "rin|role:rin", mood: "开心", updatedAt: after(5) },
    ]), [false, true]);
  });

  it("does not play when the role or session changes (role switch)", () => {
    assert.deepEqual(run([
      { scope: "rin|role:rin", mood: "平静", updatedAt: after(-60) },
      { scope: "natsu|role:natsu", mood: "开心", updatedAt: after(5) },
    ]), [false, false]);
  });

  it("does not play a mood set before the chat came into view (fresh copy replacing a cached session, reload)", () => {
    assert.deepEqual(run([
      { scope: "natsu|role:natsu", mood: "平静", updatedAt: after(-600) },
      { scope: "natsu|role:natsu", mood: "开心", updatedAt: after(-120) },
    ]), [false, false]);
  });

  it("does not play the same mood again, or a fallback mood without a stamp", () => {
    assert.deepEqual(run([
      { scope: "rin|role:rin", mood: "平静", updatedAt: after(-60) },
      { scope: "rin|role:rin", mood: "平静", updatedAt: after(5) },
      { scope: "rin|role:rin", mood: "开心", updatedAt: "" },
      { scope: "rin|role:rin", mood: "", updatedAt: after(9) },
    ]), [false, false, false, false]);
  });

  it("keeps the baseline moving so each real change plays once", () => {
    assert.deepEqual(run([
      { scope: "rin|role:rin", mood: "平静", updatedAt: after(-60) },
      { scope: "rin|role:rin", mood: "开心", updatedAt: after(5) },
      { scope: "rin|role:rin", mood: "开心", updatedAt: after(5) },
      { scope: "rin|role:rin", mood: "难过", updatedAt: after(9) },
    ]), [false, true, false, true]);
  });

  it("accepts the backend's microsecond ISO stamps", () => {
    assert.deepEqual(run([
      { scope: "rin|role:rin", mood: "平静", updatedAt: "" },
      { scope: "rin|role:rin", mood: "开心", updatedAt: "2026-09-25T10:00:03.123456+08:00" },
    ]), [false, true]);
  });
});
