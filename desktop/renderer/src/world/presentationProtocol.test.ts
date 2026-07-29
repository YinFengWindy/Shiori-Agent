import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { parsePerformancePlan, parsePresentationState } from "./presentationProtocol";

const plan = {
  schemaVersion: 1,
  planId: "plan-1",
  worldId: "world-1",
  eventId: "event-1",
  sourceSequence: 2,
  cues: [{
    schemaVersion: 1,
    cueId: "cue-1",
    planId: "plan-1",
    sequence: 0,
    kind: "dialogue",
    payload: { content: "你好" },
    parallelGroup: null,
    blocking: true,
    completionState: "completed",
    skipState: "skipped",
    checkpoint: true,
  }],
};

describe("parsePerformancePlan", () => {
  it("accepts a versioned cue envelope", () => {
    assert.deepEqual(parsePerformancePlan(plan), plan);
  });

  it("rejects a cue that belongs to another plan", () => {
    assert.throws(() => parsePerformancePlan({
      ...plan,
      cues: [{ ...plan.cues[0], planId: "plan-2" }],
    }), /cue planId/);
  });

  it("rejects non-contiguous cue sequences", () => {
    assert.throws(() => parsePerformancePlan({
      ...plan,
      cues: [{ ...plan.cues[0], sequence: 1 }],
    }), /contiguous/);
  });
});

describe("parsePresentationState", () => {
  it("accepts a persisted cursor and keeps the stable plan identity", () => {
    const state = parsePresentationState({
      session: {
        worldId: "world-1",
        lastPresentedEventSequence: 0,
        activePlanId: "plan-1",
        activeCueIndex: 0,
        status: "playing",
        updatedAt: "2026-07-29T00:00:00+00:00",
      },
      plans: [plan],
    });
    assert.equal(state.session.activePlanId, "plan-1");
    assert.equal(state.plans[0].planId, "plan-1");
  });

  it("rejects an unsupported session status", () => {
    assert.throws(() => parsePresentationState({
      session: {
        worldId: "world-1",
        lastPresentedEventSequence: 0,
        activePlanId: null,
        activeCueIndex: 0,
        status: "stopped",
        updatedAt: "2026-07-29T00:00:00+00:00",
      },
      plans: [],
    }), /session status/);
  });
});
