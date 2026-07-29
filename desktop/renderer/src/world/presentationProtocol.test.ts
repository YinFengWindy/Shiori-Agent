import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { parsePerformancePlan } from "./presentationProtocol";

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
