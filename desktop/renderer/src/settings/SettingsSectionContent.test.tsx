/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SettingsSectionContent } from "./SettingsSectionContent";
import type { RoleRecord, SettingsFormData } from "../shared/types";

function createRole(overrides: Partial<RoleRecord> = {}): RoleRecord {
  return {
    id: overrides.id ?? "mira",
    name: overrides.name ?? "Mira",
    description: overrides.description ?? "",
    system_prompt: overrides.system_prompt ?? "",
    runtime_config: overrides.runtime_config ?? {},
    avatar: overrides.avatar ?? null,
    avatar_abs: overrides.avatar_abs ?? null,
    chat_background: overrides.chat_background ?? null,
    chat_background_abs: overrides.chat_background_abs ?? null,
    illustrations: overrides.illustrations ?? [],
    illustrations_abs: overrides.illustrations_abs ?? [],
    created_at: overrides.created_at ?? "2026-07-05T20:00:00+08:00",
    updated_at: overrides.updated_at ?? "2026-07-05T20:00:00+08:00",
  };
}

function createDraft(): SettingsFormData {
  return {
    models: {
      provider: "openai",
      mainModel: "gpt-4.1",
      mainApiKey: "sk-main",
      mainBaseUrl: "",
      enableThinking: true,
      reasoningEffort: "",
      multimodal: true,
      fastModel: "",
      fastApiKey: "",
      fastBaseUrl: "",
      agentModel: "",
      agentApiKey: "",
      agentBaseUrl: "",
      vlModel: "",
      vlApiKey: "",
      vlBaseUrl: "",
    },
    channels: {
      telegramToken: "",
      telegramAllowFrom: [],
      telegramChannelName: "",
      qqBotUin: "",
      qqAllowFrom: [],
      qqWebsocketOpenTimeoutSeconds: 20,
      qqGroups: [],
      qqbotAppId: "",
      qqbotClientSecret: "",
      qqbotAllowFrom: [],
      qqbotGroups: [],
      feishuAppId: "",
      feishuAppSecret: "",
      feishuAllowFrom: [],
      feishuDomain: "",
      cliSocket: "",
      cliSessionKey: "",
      roleBindings: [],
    },
    memory: {
      enabled: true,
      engine: "",
      embeddingModel: "",
      embeddingApiKey: "",
      embeddingBaseUrl: "",
      outputDimensionality: "",
    },
    proactive: {
      enabled: false,
      profile: "",
      targetChannel: "",
      targetChatId: "",
      targetRoleId: "",
      agentMaxSteps: 6,
      agentContentLimit: 1200,
      agentWebFetchMaxChars: 8000,
      agentContextProb: 0.2,
      agentDeliveryCooldownHours: 8,
      driftEnabled: false,
      driftMaxSteps: 4,
      driftMinIntervalHours: 6,
    },
    integrations: {
      fitbitEnabled: false,
      novelaiEnabled: false,
      novelaiToken: "",
      novelaiBaseUrl: "",
      novelaiDefaultModel: "",
      novelaiNsfwModel: "",
      novelaiNsfwEnabled: false,
      novelaiAddQualityTags: true,
      novelaiUndesiredContentPreset: 1,
      novelaiAllowTxt2img: true,
      novelaiAllowImg2img: true,
      novelaiAutoWritebackRoleAssets: false,
      novelaiMaxSteps: 28,
      novelaiMaxPixels: 1048576,
      peerAgents: [],
    },
    advanced: {
      systemPrompt: "",
      maxTokens: 4096,
      maxIterations: 8,
      devMode: false,
      memoryWindow: 20,
      searchEnabled: true,
      spawnEnabled: false,
      memoryOptimizerEnabled: false,
      memoryOptimizerIntervalSeconds: 300,
      wiringContext: "",
      wiringMemory: "",
      wiringToolsets: [],
      pluginsRawToml: "",
    },
  };
}

function renderSection(section: Parameters<typeof SettingsSectionContent>[0]["section"], subsectionId: string, draftOverrides: Partial<SettingsFormData> = {}): string {
  const draft = createDraft();
  Object.assign(draft, draftOverrides);

  return renderToStaticMarkup(
    <SettingsSectionContent
      section={section}
      subsectionId={subsectionId}
      draft={draft}
      roles={[createRole()]}
      dirty={false}
      updateDraft={() => undefined}
      updateProactiveTargetChannel={() => undefined}
      updateProactiveTargetRoleId={() => undefined}
    />,
  );
}

describe("SettingsSectionContent", () => {
  it("renders layered cards and inline empty-state guidance for the models section", () => {
    const markup = renderSection("models", "main");

    assert.match(markup, />主模型连接</);
    assert.match(markup, />对话能力</);
    assert.match(markup, /用途：/);
    assert.match(markup, /覆盖默认模型服务地址。/);
    assert.match(markup, /留空时使用 provider 默认地址。/);
  });

  it("renders proactive target statuses and inline dependency hints", () => {
    const markup = renderSection("proactive", "general");

    assert.match(markup, />主动推送未启用</);
    assert.match(markup, />目标角色未配置</);
    assert.match(markup, />关闭时其余 proactive 参数不会生效。</);
  });

  it("keeps low-frequency integration options behind the expandable block", () => {
    const markup = renderSection("integrations", "novelai");

    assert.match(markup, />接入配置</);
    assert.match(markup, />生成默认值</);
    assert.match(markup, />展开更多选项</);
    assert.match(markup, />NovelAI 未启用</);
  });
});
