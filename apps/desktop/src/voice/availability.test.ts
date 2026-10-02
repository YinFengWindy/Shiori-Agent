import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  applyVoiceAvailability,
  isVoiceHotkeyAvailable,
  type VoiceAvailabilityEffects,
} from "./availability.js";

function recorder() {
  const calls: string[] = [];
  const effects: VoiceAvailabilityEffects = {
    start: () => { calls.push("start"); },
    stop: () => { calls.push("stop"); },
    stopAfterCurrentPress: () => { calls.push("stopAfterCurrentPress"); },
    cancelCurrentTurn: () => { calls.push("cancelCurrentTurn"); },
  };
  return { calls, effects };
}

describe("voice hotkey availability", () => {
  it("is available only when voice is enabled and a ready visible surface declares a target", () => {
    assert.equal(
      isVoiceHotkeyAvailable({ voiceEnabled: true, targetAvailable: true }),
      true,
    );
    assert.equal(
      isVoiceHotkeyAvailable({ voiceEnabled: false, targetAvailable: true }),
      false,
    );
    assert.equal(
      isVoiceHotkeyAvailable({ voiceEnabled: true, targetAvailable: false }),
      false,
      "a stopped pet has no surface to speak through",
    );
    assert.equal(
      isVoiceHotkeyAvailable({ voiceEnabled: true, targetAvailable: false }),
      false,
      "hiding the pet must disarm the hotkey",
    );
  });

  it("arms the hotkey when voice becomes available", () => {
    const { calls, effects } = recorder();

    applyVoiceAvailability(true, true, effects);

    assert.deepEqual(calls, ["start"]);
  });

  it("aborts the in-flight turn when the target goes away", () => {
    const { calls, effects } = recorder();

    applyVoiceAvailability(false, true, effects);

    assert.deepEqual(calls, ["stop", "cancelCurrentTurn"]);
  });

  it("lets the current press finish when only settings changed", () => {
    const { calls, effects } = recorder();

    applyVoiceAvailability(false, false, effects);

    assert.deepEqual(calls, ["stopAfterCurrentPress"]);
  });
});
