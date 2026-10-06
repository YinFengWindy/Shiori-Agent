import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { VoiceProviderDescriptor } from "../../../src/bridge/shared";
import { voiceEmotionOptions, voiceProviderOptions } from "./voiceProviders";

const providers: VoiceProviderDescriptor[] = [
  { id: "speech", label: "Local speech", kind: "tts", plugin_id: "local", available: true, capabilities: { emotions: ["bright"], voice_cloning: false } },
  { id: "recognition", label: "Recognition", kind: "asr", plugin_id: "asr", available: true, capabilities: { emotions: [], voice_cloning: false } },
];

describe("voice provider options", () => {
  it("filters the slot and preserves a missing selection as unavailable", () => {
    assert.deepEqual(voiceProviderOptions(providers, "tts", "missing"), [
      { value: "speech", label: "Local speech", disabled: false },
      { value: "missing", label: "missing（不可用）", disabled: true },
    ]);
  });

  it("does not duplicate unavailable descriptors or silently replace a stored emotion", () => {
    assert.deepEqual(voiceProviderOptions([{ ...providers[0], available: false }], "tts", "speech"), [{ value: "speech", label: "Local speech（不可用）", disabled: true }]);
    assert.deepEqual(voiceEmotionOptions(["bright"], "calm"), [
      { value: "", label: "自动判断" }, { value: "bright", label: "bright" }, { value: "calm", label: "calm（不受支持）", disabled: true },
    ]);
  });

  it("uses an empty selection only as a disabled placeholder", () => {
    assert.deepEqual(voiceProviderOptions([], "tts", ""), [{ value: "", label: "未选择", disabled: true }]);
    assert.equal(voiceProviderOptions(providers, "tts", "speech").some((option) => option.value === ""), false);
  });
});
