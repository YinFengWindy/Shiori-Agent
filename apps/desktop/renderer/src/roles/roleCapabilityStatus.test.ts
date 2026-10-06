import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { SettingsFormData } from "../../../src/bridge/shared";
import { globalVoiceOutputEnabled, roleVoiceStatus } from "./roleCapabilityStatus";

function voiceSettings(voice: Partial<SettingsFormData["voice"]>): Pick<SettingsFormData, "voice"> {
  return { voice: { enabled: false, hotkey: "", microphoneDeviceId: "", asrProvider: "", ttsProvider: "", ...voice } };
}

describe("roleVoiceStatus", () => {
  it("reports a missing plugin without losing the selected voice", () => {
    assert.deepEqual(roleVoiceStatus({ roleEnabled: true, voiceId: "saved-voice", globalEnabled: true, providerAvailable: false }), { label: "服务商不可用", tone: "attention" });
  });
  it("does not claim 已启用 while no voice is chosen and global voice is off", () => {
    const status = roleVoiceStatus({ roleEnabled: true, voiceId: "", globalEnabled: false });
    assert.equal(status.label, "全局语音已关闭");
    assert.equal(status.tone, "attention");
  });

  it("asks for a voice once global voice is on", () => {
    assert.deepEqual(roleVoiceStatus({ roleEnabled: true, voiceId: " ", globalEnabled: true }), { label: "未设置音色", tone: "attention" });
  });

  it("reads 已启用 only when the role, the global switch and a voice all hold", () => {
    assert.deepEqual(roleVoiceStatus({ roleEnabled: true, voiceId: "female-1", globalEnabled: true }), { label: "已启用", tone: "on" });
  });

  it("reads 未启用 whenever the role's own switch is off", () => {
    assert.deepEqual(roleVoiceStatus({ roleEnabled: false, voiceId: "", globalEnabled: false }), { label: "未启用", tone: "off" });
  });

  it("does not block on the global switch while settings are still loading", () => {
    assert.equal(roleVoiceStatus({ roleEnabled: true, voiceId: "female-1", globalEnabled: null }).label, "已启用");
  });
});

describe("globalVoiceOutputEnabled", () => {
  it("needs both the voice switch and the TTS switch", () => {
    assert.equal(globalVoiceOutputEnabled(voiceSettings({ enabled: true, ttsEnabled: true })), true);
    assert.equal(globalVoiceOutputEnabled(voiceSettings({ enabled: true, ttsEnabled: false })), false);
    assert.equal(globalVoiceOutputEnabled(voiceSettings({ enabled: false, ttsEnabled: true })), false);
  });

  it("falls back to the voice switch when the TTS switch is unset, and is unknown without settings", () => {
    assert.equal(globalVoiceOutputEnabled(voiceSettings({ enabled: true })), true);
    assert.equal(globalVoiceOutputEnabled(null), null);
  });
});
