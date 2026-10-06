/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleRecord } from "@yinfengwindy/shiori-sdk";
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
    voiceMoodEmotions: overrides.voiceMoodEmotions ?? { 开心: "happy" },
  };
}

describe("roleVoiceConfig", () => {
  it("normalizes legacy voice fields without discarding provider emotion identifiers", () => {
    assert.deepEqual(readRoleVoiceConfig(role({ tts: { voice_id: "voice-1", speed: 1.2, mood_tts_emotions: { 开心: "happy", 无效: "unknown" } } })), {
      enabled: true,
      provider: "minimax",
      ownership: "external",
      voiceId: "voice-1",
      voiceName: "",
      speed: 1.2,
      moodTtsEmotions: { 开心: "happy", 无效: "unknown" },
      providerSettings: { minimax: { ownership: "external", voiceId: "voice-1", voiceName: "", speed: 1.2, moodTtsEmotions: { 开心: "happy", 无效: "unknown" } } },
    });
  });

  it("writes role voice data without dropping unrelated runtime fields", () => {
    const next = writeRoleVoiceConfigToRuntimeConfig(
      { keep: true, tts: { provider: "legacy" } },
      form({ voiceProvider: "minimax" }),
    );
    assert.equal(next.keep, true);
    const settings = { ownership: "external", voice_id: "voice-1", voice_name: "Mira", speed: 1.2, mood_tts_emotions: { 开心: "happy" } };
    assert.deepEqual(next.tts, { enabled: true, provider: "minimax", ...settings, providers: { minimax: settings } });
  });

  it("recognizes an unchanged role voice form", () => {
    assert.equal(roleVoiceConfigEqual(form(), readRoleVoiceConfig(role({ tts: { voice_id: "voice-1", voice_name: "Mira", speed: 1.2, mood_tts_emotions: { 开心: "happy" } } }))), true);
    assert.equal(roleVoiceConfigEqual(form({ voiceProvider: "other" }), readRoleVoiceConfig(role({ tts: { provider: "minimax", voice_id: "voice-1", voice_name: "Mira", speed: 1.2, mood_tts_emotions: { 开心: "happy" } } }))), false);
    assert.equal(roleVoiceConfigEqual(form({ voiceOwnership: "shiori_managed" }), readRoleVoiceConfig(role({ tts: { provider: "minimax", ownership: "external", voice_id: "voice-1", voice_name: "Mira", speed: 1.2, mood_tts_emotions: { 开心: "happy" } } }))), false);
  });

  it("prefers scoped settings and preserves inactive providers and plugin-specific fields", () => {
    const runtime = { tts: { provider: "local", voice_id: "wrong-active-mirror", providers: {
      local: { voice_id: "local-voice", speed: 1.1, mood_tts_emotions: { 开心: "bright" }, reference_audio: "ref.wav" },
      minimax: { voice_id: "saved-cloud", ownership: "shiori_managed" },
    } } };
    const persisted = readRoleVoiceConfig(role(runtime));
    assert.equal(persisted.voiceId, "local-voice");
    assert.deepEqual(persisted.moodTtsEmotions, { 开心: "bright" });
    const draft = { ...form({ voiceProvider: "local", voiceId: "changed-local", voiceMoodEmotions: { 开心: "bright" } }), voiceProviderSettings: persisted.providerSettings };
    const next = writeRoleVoiceConfigToRuntimeConfig(runtime, draft);
    assert.equal(readRoleVoiceConfig(role(next)).voiceId, "changed-local");
    assert.deepEqual(readRoleVoiceConfig(role(next)).providerSettings.minimax, persisted.providerSettings.minimax);
    assert.match(JSON.stringify(next), /reference_audio/);
    assert.equal(roleVoiceConfigEqual(draft, persisted), false);
    assert.equal(roleVoiceConfigEqual(draft, readRoleVoiceConfig(role(next))), true);
  });

  it("never adopts another provider's mirrored voice or replaces an explicit empty selection", () => {
    const runtime = { tts: { provider: "unconfigured", voice_id: "old-cloud", providers: { minimax: { voice_id: "old-cloud" } } } };
    assert.equal(readRoleVoiceConfig(role(runtime)).voiceId, "");
    assert.equal(readRoleVoiceConfig(role({ tts: { provider: "" } })).provider, "");
    const result = writeRoleVoiceConfigToRuntimeConfig({}, form({ voiceProvider: "", voiceId: "" }));
    assert.equal(readRoleVoiceConfig(role(result)).provider, "");
  });

});
