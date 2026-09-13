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
    channels: {
      telegramToken: "telegram-token",
      qqBotUin: "10001",
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
      asrBaseUrl: "https://asr.tencentcloudapi.com/",
      asrSecretId: "secret-id",
      asrSecretKey: "secret-key",
      ttsProvider: "minimax",
      ttsBaseUrl: "https://api.minimaxi.com/v1/t2a_v2",
      ttsModel: "speech-2.8-turbo",
      ttsApiKey: "tts-key",
      ttsVolume: 2,
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
      consolidationInputTokenThreshold: 75000
    },
  };
}

describe("SettingsSectionContent", () => {
  const draft = createSettingsFormData();
  const updateDraft = () => undefined;

  it("routes every settings domain to its editor", () => {
    const cases = [
      { sectionId: "models", subsectionId: "catalog", expected: "gpt-agent" },
      { sectionId: "channels", subsectionId: "qq", expected: "10001" },
      { sectionId: "memory", subsectionId: "embedding", expected: "embed-model" },
      { sectionId: "voice", subsectionId: "provider", expected: "secret-id" },
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
    assert.match(markup, />https:\/\/agent\.example</);
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

  it("renders the global TTS volume control", () => {
    const markup = renderToStaticMarkup(
      <SettingsSectionContent
        sectionId="voice"
        subsectionId="provider"
        draft={draft}
        updateDraft={updateDraft}
      />,
    );

    assert.match(markup, /aria-label="TTS 音量"/);
    assert.match(markup, /type="range"/);
    assert.match(markup, /value="2"/);
  });
});
