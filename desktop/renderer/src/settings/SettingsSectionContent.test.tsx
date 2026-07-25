/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { SettingsFormData } from "../../../src/shared.js";
import { SettingsSectionContent } from "./SettingsSectionContent.js";

function createSettingsFormData(): SettingsFormData {
  return {
    models: {
      provider: "openai",
      mainModel: "gpt-main",
      mainApiKey: "main-key",
      mainBaseUrl: "https://main.example",
      enableThinking: true,
      reasoningEffort: "medium",
      multimodal: true,
      fastModel: "gpt-fast",
      fastApiKey: "fast-key",
      fastBaseUrl: "https://fast.example",
      agentModel: "gpt-agent",
      agentApiKey: "agent-key",
      agentBaseUrl: "https://agent.example",
      vlModel: "gpt-vl",
      vlApiKey: "vl-key",
      vlBaseUrl: "https://vl.example",
    },
    channels: {
      telegramToken: "telegram-token",
      qqBotUin: "10001",
      qqBotAppId: "qq-app",
      qqBotClientSecret: "qq-secret",
    },
    memory: {
      enabled: true,
      engine: "default_memory",
      embeddingModel: "embed-model",
      embeddingApiKey: "embed-key",
      embeddingBaseUrl: "https://embed.example",
      outputDimensionality: "1536",
    },
    integrations: {
      novelaiEnabled: true,
      novelaiToken: "novel-token",
      novelaiNsfwEnabled: false,
      novelaiAddQualityTags: true,
      novelaiUndesiredContentPreset: 1,
      novelaiAutoWritebackRoleAssets: true,
    },
    advanced: {
      systemPrompt: "system prompt",
      maxTokens: 4000,
      maxIterations: 10,
      devMode: false,
      memoryWindow: 20,
      searchEnabled: true,
      spawnEnabled: true,
      memoryOptimizerEnabled: false,
      memoryOptimizerIntervalSeconds: 3600,
      pluginsRawToml: "",
    },
  };
}

describe("SettingsSectionContent", () => {
  const draft = createSettingsFormData();
  const updateDraft = () => undefined;

  it("routes every settings domain to its editor", () => {
    const cases = [
      { sectionId: "models", subsectionId: "main", expected: "gpt-main" },
      { sectionId: "channels", subsectionId: "qqbot", expected: "qq-app" },
      { sectionId: "memory", subsectionId: "embedding", expected: "embed-model" },
      { sectionId: "integrations", subsectionId: "novelai", expected: "novel-token" },
      { sectionId: "advanced", subsectionId: "general", expected: "system prompt" },
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

  it("binds the Agent subsection to the model settings domain", () => {
    const markup = renderToStaticMarkup(
      <SettingsSectionContent
        sectionId="models"
        subsectionId="agent"
        draft={draft}
        updateDraft={updateDraft}
      />,
    );

    assert.match(markup, /Agent 模型/);
    assert.match(markup, /value="gpt-agent"/);
    assert.match(markup, /value="agent-key"/);
  });
});
