/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleRecord } from "@shiori/sdk";
import type { RoleFormState } from "../shared/types";
import { readRoleVoiceConfig, roleVoiceConfigEqual, writeRoleVoiceConfigToRuntimeConfig } from "./roleVoiceConfig.js";

function role(runtime_config: Record<string, unknown>): Pick<RoleRecord, "runtime_config"> {
  return { runtime_config };
}

function form(overrides: Partial<RoleFormState> = {}): Pick<RoleFormState, "voiceEnabled" | "voiceProvider" | "voiceOwnership" | "voiceId" | "voiceName" | "voiceSpeed" | "voiceMoodEmotions"> {
  return {
    voiceEnabled: overrides.voiceEnabled ?? true,
    voiceProvider: overrides.voiceProvider ?? "minimax",
    voiceOwnership: overrides.voiceOwnership ?? "external",
    voiceId: overrides.voiceId ?? "voice-1",
    voiceName: overrides.voiceName ?? "Mira",
    voiceSpeed: overrides.voiceSpeed ?? 1.2,
    voiceMoodEmotions: overrides.voiceMoodEmotions ?? { 开心: "happy", 无效: "unknown" },
  };
}

describe("roleVoiceConfig", () => {
  it("normalizes persisted voice fields and removes unsupported emotions", () => {
    assert.deepEqual(readRoleVoiceConfig(role({ tts: { voice_id: "voice-1", speed: 1.2, mood_tts_emotions: { 开心: "happy", 无效: "unknown" } } })), {
      enabled: true,
      provider: "minimax",
      ownership: "external",
      voiceId: "voice-1",
      voiceName: "",
      speed: 1.2,
      moodTtsEmotions: { 开心: "happy" },
    });
  });

  it("writes role voice data without dropping unrelated runtime fields", () => {
    const next = writeRoleVoiceConfigToRuntimeConfig(
      { keep: true, tts: { provider: "legacy" } },
      form({ voiceProvider: "minimax" }),
    );
    assert.equal(next.keep, true);
    assert.deepEqual(next.tts, { enabled: true, provider: "minimax", ownership: "external", voice_id: "voice-1", voice_name: "Mira", speed: 1.2, mood_tts_emotions: { 开心: "happy" } });
  });

  it("recognizes an unchanged role voice form", () => {
    assert.equal(roleVoiceConfigEqual(form(), readRoleVoiceConfig(role({ tts: { voice_id: "voice-1", voice_name: "Mira", speed: 1.2, mood_tts_emotions: { 开心: "happy" } } }))), true);
    assert.equal(roleVoiceConfigEqual(form({ voiceProvider: "other" }), readRoleVoiceConfig(role({ tts: { provider: "minimax", voice_id: "voice-1", voice_name: "Mira", speed: 1.2, mood_tts_emotions: { 开心: "happy" } } }))), false);
    assert.equal(roleVoiceConfigEqual(form({ voiceOwnership: "shiori_managed" }), readRoleVoiceConfig(role({ tts: { provider: "minimax", ownership: "external", voice_id: "voice-1", voice_name: "Mira", speed: 1.2, mood_tts_emotions: { 开心: "happy" } } }))), false);
  });

});
