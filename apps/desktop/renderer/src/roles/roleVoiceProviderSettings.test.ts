import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createEmptyRoleForm } from "../app/appState";
import { normalizeMoodTtsEmotions, selectRoleVoiceProvider } from "./roleVoiceProviderSettings";

describe("role voice provider switching", () => {
  it("starts a new provider empty and restores unsaved voice and emotion edits on return", () => {
    const original = { ...createEmptyRoleForm(), voiceId: "cloud-clone", voiceOwnership: "shiori_managed" as const, voiceName: "晨雾", voiceSpeed: 1.4, voiceMoodEmotions: { 开心: "happy" } };
    const local = selectRoleVoiceProvider(original, "local-tts");
    assert.equal(local.voiceId, "");
    assert.equal(local.voiceOwnership, "external");
    assert.equal(local.voiceSpeed, 1);
    assert.deepEqual(local.voiceMoodEmotions, {});
    const restored = selectRoleVoiceProvider({ ...local, voiceId: "local-character", voiceMoodEmotions: { 开心: "bright" } }, "minimax");
    assert.equal(restored.voiceId, "cloud-clone");
    assert.equal(restored.voiceOwnership, "shiori_managed");
    assert.equal(restored.voiceSpeed, 1.4);
    assert.deepEqual(restored.voiceMoodEmotions, { 开心: "happy" });
    assert.equal(restored.voiceProviderSettings?.["local-tts"].voiceId, "local-character");
    assert.deepEqual(restored.voiceProviderSettings?.["local-tts"].moodTtsEmotions, { 开心: "bright" });
    assert.equal(selectRoleVoiceProvider(restored, "minimax"), restored);
  });

  it("normalizes empty mappings while retaining opaque provider values", () => {
    assert.deepEqual(normalizeMoodTtsEmotions({ " 开心 ": " cheerful:0.8 ", "": "happy", 平静: " " }), { 开心: "cheerful:0.8" });
  });
});
