/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { DesktopApi, SettingsFormData, SettingsSnapshot } from "../../../src/shared.js";
import {
  loadSettingsPageData,
  saveSettingsPageData,
  shouldRetryFailedSettingsLoad,
} from "./settingsPersistence.js";

function createSettingsFormData(
  overrides: Partial<SettingsFormData["models"]> = {},
): SettingsFormData {
  return {
    models: {
      provider: "openai",
      mainModel: overrides.mainModel ?? "gpt-main",
      mainApiKey: "",
      mainBaseUrl: "",
      enableThinking: false,
      reasoningEffort: "medium",
      multimodal: false,
      fastModel: "gpt-fast",
      fastApiKey: "",
      fastBaseUrl: "",
      agentModel: "gpt-agent",
      agentApiKey: "",
      agentBaseUrl: "",
      vlModel: "gpt-vl",
      vlApiKey: "",
      vlBaseUrl: "",
    },
    channels: {
      telegramToken: "",
      qqBotUin: "",
      qqBotAppId: "",
      qqBotClientSecret: "",
    },
    memory: {
      enabled: true,
      engine: "default",
      embeddingModel: "",
      embeddingApiKey: "",
      embeddingBaseUrl: "",
      outputDimensionality: "",
    },
    integrations: {
      novelaiEnabled: false,
      novelaiToken: "",
      novelaiNsfwEnabled: false,
      novelaiAddQualityTags: false,
      novelaiUndesiredContentPreset: 0,
      novelaiAutoWritebackRoleAssets: false,
    },
    advanced: {
      systemPrompt: "",
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

function createSettingsSnapshot(
  overrides: Partial<SettingsFormData["models"]> = {},
): SettingsSnapshot {
  return {
    configPath: "D:\\Coding\\Shiori\\config.toml",
    formData: createSettingsFormData(overrides),
  };
}

describe("shouldRetryFailedSettingsLoad", () => {
  it("retries once the bridge recovers from a failed settings load", () => {
    assert.equal(shouldRetryFailedSettingsLoad({ bridgeReady: true, loadError: "bridge offline" }), true);
    assert.equal(shouldRetryFailedSettingsLoad({ bridgeReady: false, loadError: "bridge offline" }), false);
  });
});

describe("loadSettingsPageData", () => {
  it("loads only persisted runtime settings", async () => {
    const snapshot = createSettingsSnapshot();
    const loaded = await loadSettingsPageData({
      readSettings: async () => snapshot,
    } satisfies Pick<DesktopApi, "readSettings">);

    assert.deepEqual(loaded.snapshot, snapshot);
  });
});

describe("saveSettingsPageData", () => {
  it("does not touch role-owned channel bindings", async () => {
    const calls: string[] = [];
    const persistedSnapshot = createSettingsSnapshot({ mainModel: "saved-model" });
    const result = await saveSettingsPageData(
      {
        saveSettings: async () => {
          calls.push("saveSettings");
          return {
            ok: true,
            restart: { ok: true, running: true, lastError: null },
            health: { ok: true, message: "ok" },
          };
        },
        readSettings: async () => {
          calls.push("readSettings");
          return persistedSnapshot;
        },
      } satisfies Pick<DesktopApi, "readSettings" | "saveSettings">,
      createSettingsFormData({ mainModel: "draft-model" }),
    );

    assert.deepEqual(calls, ["saveSettings", "readSettings"]);
    assert.equal(result.snapshot.formData.models.mainModel, "saved-model");
    assert.equal(result.nextDraft.channels.telegramToken, "");
  });
});
