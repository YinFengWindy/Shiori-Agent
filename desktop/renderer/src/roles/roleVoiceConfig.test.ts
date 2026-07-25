/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { deleteManagedVoiceAssets, managedVoiceAssetsForRole, queueManagedVoiceAssetDeletion, readRoleVoiceConfig, roleVoiceConfigEqual, writeRoleVoiceConfigToRuntimeConfig } from "./roleVoiceConfig.js";

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

  it("queues only unique Shiori-managed voice assets for deletion", () => {
    const managed = {
      voiceProvider: "minimax",
      voiceId: "Shiori_voice123",
      voiceOwnership: "shiori_managed" as const,
      pendingVoiceAssetDeletes: [],
    };

    const queued = queueManagedVoiceAssetDeletion(managed);

    assert.deepEqual(queued, [{
      provider: "minimax",
      voiceId: "Shiori_voice123",
      ownership: "shiori_managed",
    }]);
    assert.deepEqual(queueManagedVoiceAssetDeletion({ ...managed, pendingVoiceAssetDeletes: queued }), queued);
    assert.deepEqual(queueManagedVoiceAssetDeletion({ ...managed, voiceOwnership: "external" }), []);
  });

  it("retains only managed voice assets whose provider deletion failed", async () => {
    const assets = [
      { provider: "minimax", voiceId: "Shiori_ok", ownership: "shiori_managed" as const },
      { provider: "minimax", voiceId: "Shiori_retry", ownership: "shiori_managed" as const },
    ];
    const calls: string[] = [];
    const failed = await deleteManagedVoiceAssets(assets, async (request) => {
      calls.push(String(request.payload.voice_id));
      return {
        id: "delete",
        type: "response",
        method: request.method,
        payload: {},
        error: request.payload.voice_id === "Shiori_retry"
          ? { code: "provider_error", message: "failed" }
          : null,
      };
    });

    assert.deepEqual(calls, ["Shiori_ok", "Shiori_retry"]);
    assert.deepEqual(failed, [assets[1]]);
  });

  it("requires provider cleanup only for a managed role voice", () => {
    assert.deepEqual(managedVoiceAssetsForRole(role({
      tts: {
        provider: "minimax",
        ownership: "shiori_managed",
        voice_id: "Shiori_voice123",
      },
    })), [{
      provider: "minimax",
      voiceId: "Shiori_voice123",
      ownership: "shiori_managed",
    }]);
    assert.deepEqual(managedVoiceAssetsForRole(role({
      tts: {
        provider: "minimax",
        ownership: "external",
        voice_id: "public_voice",
      },
    })), []);
  });
});
