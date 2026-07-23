import assert from "node:assert/strict";
import test from "node:test";
import {
  companionObservationCooldownMs,
  companionObservationIdleThresholdSeconds,
  shouldRequestCompanionObservation,
} from "./scheduler.js";

test("companion observation requires enabled, idle, cooled-down state", () => {
  const ready = {
    enabled: true,
    busy: false,
    nowMs: companionObservationCooldownMs + 1,
    lastObservationAtMs: 0,
    lastInteractionAtMs: 0,
    idleSeconds: companionObservationIdleThresholdSeconds,
  };
  assert.equal(shouldRequestCompanionObservation(ready), true);
  assert.equal(shouldRequestCompanionObservation({ ...ready, enabled: false }), false);
  assert.equal(shouldRequestCompanionObservation({ ...ready, busy: true }), false);
  assert.equal(shouldRequestCompanionObservation({ ...ready, idleSeconds: 0 }), false);
  assert.equal(shouldRequestCompanionObservation({ ...ready, lastInteractionAtMs: ready.nowMs - 1 }), false);
});
