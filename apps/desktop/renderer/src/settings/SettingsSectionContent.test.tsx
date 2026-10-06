/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { SettingsFormData } from "../../../src/bridge/shared.js";
import { SettingsSectionContent } from "./SettingsSectionContent.js";

function createSettingsFormData(): SettingsFormData {
  return {
    proactiveStrategies: {},
    models: {
      registrations: [{ id: "00000000-0000-4000-a000-000000000001", provider: "openai", model: "gpt-agent", apiKey: "agent-key", baseUrl: "https://agent.example", effort: "high" }],
    },
    memory: {
      enabled: true,
      engine: "default_memory",
      embeddingModel: "embed-model",
      embeddingApiKey: "embed-key",
      embeddingBaseUrl: "https://embed.example",
      outputDimensionality: "1536",
    },
    voice: {
      enabled: true,
      hotkey: "Ctrl+Space",
      microphoneDeviceId: "",
      asrProvider: "tencent",
      ttsProvider: "minimax",
    },
    advanced: {
      maxTokens: 4000,
      maxIterations: 10,
      devMode: false,
      streamingEnabled: false,
      memoryWindow: 20,
      searchEnabled: true,
      spawnEnabled: true,
      memoryOptimizerEnabled: false,
      memoryOptimizerIntervalSeconds: 3600,
      contextTriggerRatio: 0.75, contextTargetRatio: 0.4, contextSafetyMarginTokens: 4096
    },
  };
}

describe("SettingsSectionContent", () => {
  const draft = createSettingsFormData();
  const updateDraft = () => undefined;

  it("routes every settings domain to its editor", () => {
    const cases = [
      { sectionId: "models", subsectionId: "catalog", expected: "gpt-agent" },
      { sectionId: "memory", subsectionId: "embedding", expected: "embed-model" },
      { sectionId: "voice", subsectionId: "provider", expected: "语音识别服务商" },
      { sectionId: "advanced", subsectionId: "general", expected: "max_tokens" },
    ] as const;

    cases.forEach(({ sectionId, subsectionId, expected }) => {
      const markup = renderToStaticMarkup(
        <SettingsSectionContent
          sectionId={sectionId}
          subsectionId={subsectionId}
          draft={draft}
          updateDraft={updateDraft}
        />,
      );
      assert.match(markup, new RegExp(expected));
    });
  });

  it("shows model registration previews without exposing detail fields", () => {
    const markup = renderToStaticMarkup(
      <SettingsSectionContent
        sectionId="models"
        subsectionId="catalog"
        draft={draft}
        updateDraft={updateDraft}
      />,
    );

    assert.doesNotMatch(markup, />名称</);
    assert.match(markup, />gpt-agent</);
    assert.match(markup, /agent\.example</);
    assert.doesNotMatch(markup, /value="gpt-agent"/);
    assert.doesNotMatch(markup, /agent-key/);
  });

  it("throws instead of silently rendering nothing for an unregistered section id", () => {
    assert.throws(() => renderToStaticMarkup(
      <SettingsSectionContent
        sectionId="does-not-exist"
        subsectionId="whatever"
        draft={draft}
        updateDraft={updateDraft}
      />,
    ), /does-not-exist/);
  });

  it("throws instead of silently rendering nothing for a standalone (non-editor) section id", () => {
    // "about" and "plugins" are registered as "standalone" — SettingsPage
    // routes those away before ever reaching SettingsSectionContent, so
    // reaching here with one is itself the invariant violation being tested.
    assert.throws(() => renderToStaticMarkup(
      <SettingsSectionContent
        sectionId="about"
        subsectionId="updates"
        draft={draft}
        updateDraft={updateDraft}
      />,
    ), /about/);
  });

  it("renders provider selectors without plugin-owned credentials", () => {
    const markup = renderToStaticMarkup(
      <SettingsSectionContent
        sectionId="voice"
        subsectionId="provider"
        draft={draft}
        updateDraft={updateDraft}
      />,
    );

    assert.match(markup, /aria-label="语音合成服务商"/);
    assert.doesNotMatch(markup, /SecretId|SecretKey|API Key|语音合成模型|TTS 音量/);
  });
});
