/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createSceneBeat, createWorldDetails } from "./testFixtures";
import { selectCurrentWorldDay, selectPendingWorldScene } from "./worldDayPresentation";

describe("worldDayPresentation", () => {
  it("selects the current day independently from historical days", () => {
    const world = createWorldDetails();

    assert.equal(selectCurrentWorldDay(world)?.dayIndex, 3);
    assert.equal(selectCurrentWorldDay(world)?.status, "current");
  });

  it("only selects an unconsumed scene event for automatic presentation", () => {
    const scene = createSceneBeat({ id: "scene-1", presentationMode: "scene" });
    const world = createWorldDetails({
      days: [{ dayIndex: 3, title: "Day 3", status: "current", events: [
        createSceneBeat({ id: "narrative-1", presentationMode: "narrative" }),
        scene,
      ] }],
      presentation: {
        session: {
          worldId: "world-1",
          lastPresentedEventSequence: 1,
          activePlanId: null,
          activeCueIndex: 0,
          status: "playing",
          updatedAt: "2026-07-31T00:00:00+00:00",
        },
        plans: [{
          schemaVersion: 1,
          planId: "plan-scene-1",
          worldId: "world-1",
          eventId: "scene-1",
          sourceSequence: 2,
          cues: [],
        }],
      },
    });

    assert.equal(selectPendingWorldScene(world)?.id, "scene-1");
    assert.equal(selectPendingWorldScene({ ...world, presentation: undefined }), null);
  });
});
