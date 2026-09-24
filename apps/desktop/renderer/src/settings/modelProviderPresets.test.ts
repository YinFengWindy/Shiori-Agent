import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { applyProviderPreset, customProviderPresetId, findProviderPreset, modelProviderOptions, modelProviderPresets } from "./modelProviderPresets";

const draft: ModelRegistrationFormData = { id: "r", provider: "", baseUrl: "", apiKey: "key", model: "m", effort: "high" };

describe("model provider presets", () => {
  it("fills provider and base URL while keeping the key, model and effort", () => {
    assert.deepEqual(applyProviderPreset(draft, "deepseek"), { ...draft, provider: "deepseek", baseUrl: "https://api.deepseek.com" });
  });

  it("recognises a saved registration regardless of case and trailing slash", () => {
    assert.equal(findProviderPreset({ provider: "DashScope", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1/" })?.id, "dashscope");
  });

  it("treats a known provider on another endpoint as custom", () => {
    assert.equal(findProviderPreset({ provider: "openai", baseUrl: "https://proxy.example/v1" }), undefined);
    assert.equal(findProviderPreset({ provider: "openai", baseUrl: "" }), undefined);
  });

  it("leaves the registration untouched for the custom choice", () => {
    assert.equal(applyProviderPreset(draft, customProviderPresetId), draft);
  });

  it("offers every preset with a unique id and the custom entry last", () => {
    assert.equal(new Set(modelProviderPresets.map((preset) => preset.id)).size, modelProviderPresets.length);
    assert.deepEqual(modelProviderOptions.at(-1), { value: customProviderPresetId, label: "自定义" });
    for (const preset of modelProviderPresets) assert.match(preset.baseUrl, /^https?:\/\/[^/]+/);
  });
});
