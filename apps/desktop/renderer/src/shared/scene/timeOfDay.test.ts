/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { scenePhaseAt } from "./timeOfDay";

/** A local-time Date on an arbitrary day at hh:mm:59.999 or hh:mm:00. */
function localTime(hours: number, minutes: number, endOfMinute = false) {
  return endOfMinute ? new Date(2026, 8, 23, hours, minutes, 59, 999) : new Date(2026, 8, 23, hours, minutes, 0, 0);
}

describe("scenePhaseAt", () => {
  it("switches at each phase boundary in local time", () => {
    assert.equal(scenePhaseAt(localTime(5, 59, true)), "night");
    assert.equal(scenePhaseAt(localTime(6, 0)), "day");
    assert.equal(scenePhaseAt(localTime(16, 59, true)), "day");
    assert.equal(scenePhaseAt(localTime(17, 0)), "dusk");
    assert.equal(scenePhaseAt(localTime(18, 59, true)), "dusk");
    assert.equal(scenePhaseAt(localTime(19, 0)), "night");
  });

  it("keeps night across midnight", () => {
    assert.equal(scenePhaseAt(localTime(23, 59, true)), "night");
    assert.equal(scenePhaseAt(localTime(0, 0)), "night");
  });
});
