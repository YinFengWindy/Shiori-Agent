/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { readRoleVoiceConfig, roleVoiceConfigEqual, writeRoleVoiceConfigToRuntimeConfig } from "./roleVoiceConfig.js";

function role(runtime_config: Record<string, unknown>): Pick<RoleRecord, "runtime_config"> {
  return { runtime_config };
}

function form(overrides: Partial<RoleFormState> = {}): Pick<RoleFormState, "voiceEnabled" | "voiceId" | "voiceName" | "voiceSpeed" | "voiceMoodEmotions"> {
  return {
    voiceEnabled: overrides.voiceEnabled ?? true,
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
      voiceId: "voice-1",
      voiceName: "",
      speed: 1.2,
      moodTtsEmotions: { 开心: "happy" },
    });
  });

  it("writes role voice data without dropping unrelated runtime fields", () => {
    const next = writeRoleVoiceConfigToRuntimeConfig({ keep: true }, form());
    assert.equal(next.keep, true);
    assert.deepEqual(next.tts, { enabled: true, provider: "minimax", voice_id: "voice-1", voice_name: "Mira", speed: 1.2, mood_tts_emotions: { 开心: "happy" } });
  });

  it("recognizes an unchanged role voice form", () => {
    assert.equal(roleVoiceConfigEqual(form(), readRoleVoiceConfig(role({ tts: { voice_id: "voice-1", voice_name: "Mira", speed: 1.2, mood_tts_emotions: { 开心: "happy" } } }))), true);
  });
});
