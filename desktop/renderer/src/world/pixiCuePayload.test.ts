import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { PresentationCue } from "./presentationProtocol";
import { cuePayloadItems, normalizedCharacterPosition, numericCueValue, stringCueValue } from "./pixiCuePayload";

describe("pixiCuePayload", () => {
  it("reads compatible fields and rejects malformed plural items", () => {
    assert.equal(stringCueValue({ asset_id: "mood-1" }, "assetId", "asset_id"), "mood-1");
    assert.equal(numericCueValue({ duration_ms: 240 }, "durationMs", "duration_ms"), 240);
    const cue: PresentationCue = {
      schemaVersion: 1,
      cueId: "cue-1",
      planId: "plan-1",
      sequence: 0,
      kind: "sprites",
      payload: { items: [{ id: "one" }, null, "bad"] },
      parallelGroup: null,
      blocking: false,
      completionState: "completed",
      skipState: "skipped",
      checkpoint: false,
    };
    assert.deepEqual(cuePayloadItems(cue, "items"), [{ id: "one" }]);
  });

  it("maps named and implicit character slots", () => {
    assert.equal(normalizedCharacterPosition("left", 0, 1), 0.22);
    assert.equal(normalizedCharacterPosition("right", 0, 1), 0.78);
    assert.equal(normalizedCharacterPosition(undefined, 1, 3), 0.5);
  });
});
