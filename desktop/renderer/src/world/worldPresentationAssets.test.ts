/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { PerformancePlan } from "./presentationProtocol";
import { hydrateWorldPresentationAssets } from "./worldPresentationAssets";
import { createWorldAssetManifest } from "./worldPresentationRenderer";

describe("worldPresentationAssets", () => {
  it("turns snapshot mood and avatar paths into a controlled Pixi manifest", () => {
    const plan: PerformancePlan = {
      schemaVersion: 1,
      planId: "plan-1",
      worldId: "world-1",
      eventId: "event-1",
      sourceSequence: 1,
      cues: [{
        schemaVersion: 1,
        cueId: "cue-1",
        planId: "plan-1",
        sequence: 0,
        kind: "sprites",
        payload: {
          items: [{
            actor_id: "resident-1",
            mood: "平静",
            assetId: "asset-mood",
            image_path: "C:/world-assets/mood.png",
            fallbackIds: ["asset-avatar"],
            fallbackAssets: [{
              assetId: "asset-avatar",
              image_path: "C:/world-assets/avatar.png",
            }],
          }],
        },
        parallelGroup: null,
        blocking: false,
        completionState: "completed",
        skipState: "skipped",
        checkpoint: false,
      }],
    };
    const hydrated = hydrateWorldPresentationAssets(
      plan,
      (path) => `shiori-asset://local/${path.includes("mood") ? "mood-token" : "avatar-token"}`,
    );

    assert.doesNotMatch(JSON.stringify(hydrated), /C:\/world-assets/);
    assert.deepEqual(createWorldAssetManifest(hydrated), [
      {
        id: "asset-mood",
        url: "shiori-asset://local/mood-token",
        kind: "character",
        fallbackIds: ["asset-avatar"],
      },
      {
        id: "asset-avatar",
        url: "shiori-asset://local/avatar-token",
        kind: "character",
        fallbackIds: undefined,
      },
    ]);
  });
});
