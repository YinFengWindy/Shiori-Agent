/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { DesktopApi, SettingsFormData, SettingsSnapshot } from "../../../src/bridge/shared.js";
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
      registrations: overrides.registrations ?? [{ id: "00000000-0000-4000-a000-000000000001", provider: "openai", model: "gpt-main", apiKey: "", baseUrl: "", effort: "none" }],
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
    voice: {
      enabled: false,
      hotkey: "Ctrl+Space",
      microphoneDeviceId: "",
      asrProvider: "tencent",
      asrBaseUrl: "https://asr.tencentcloudapi.com/",
      asrSecretId: "",
      asrSecretKey: "",
      ttsProvider: "minimax",
      ttsBaseUrl: "https://api.minimaxi.com/v1/t2a_v2",
      ttsModel: "speech-2.8-turbo",
      ttsApiKey: "",
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
    const persistedSnapshot = createSettingsSnapshot({ registrations: [{ id: "00000000-0000-4000-a000-000000000001", provider: "openai", model: "saved-model", apiKey: "", baseUrl: "", effort: "none" }] });
    const result = await saveSettingsPageData(
      {
        saveSettings: async () => {
          calls.push("saveSettings");
          return {
            ok: true,
            health: { ok: true, message: "ok" },
          };
        },
        readSettings: async () => {
          calls.push("readSettings");
          return persistedSnapshot;
        },
        invoke: async () => ({ id: "", type: "response", method: "roles.update", payload: {}, error: null }),
      } satisfies Pick<DesktopApi, "readSettings" | "saveSettings" | "invoke">,
      createSettingsFormData({ registrations: [{ id: "00000000-0000-4000-a000-000000000001", provider: "openai", model: "draft-model", apiKey: "", baseUrl: "", effort: "none" }] }),
    );

    assert.deepEqual(calls, ["saveSettings", "readSettings"]);
    assert.equal(result.snapshot.formData.models.registrations[0]?.model, "saved-model");
    assert.equal(result.nextDraft.channels.telegramToken, "");
  });

  it("commits deferred role reference changes only after settings save", async () => {
    const calls: string[] = [];
    const draft = createSettingsFormData();
    draft.pendingRoleModelUpdates = [{
      roleId: "role-1",
      runtimeConfig: { dialogue_model_registration_id: "registration-2", visual_model_registration_id: "" },
    }];
    const snapshot = createSettingsSnapshot();
    await saveSettingsPageData({
      saveSettings: async (value) => {
        calls.push(`save:${String("pendingRoleModelUpdates" in value)}`);
        return { ok: true, health: { ok: true, message: "ok" } };
      },
      invoke: async (request) => {
        calls.push(`${request.method}:${String(request.payload.role_id)}`);
        return { id: "", type: "response", method: request.method, payload: {}, error: null };
      },
      readSettings: async () => snapshot,
    }, draft);
    assert.deepEqual(calls, ["save:false", "roles.update:role-1"]);
  });

  it("keeps deferred role changes when the settings health check fails", async () => {
    const draft = createSettingsFormData();
    draft.pendingRoleModelUpdates = [{ roleId: "role-1", runtimeConfig: { dialogue_model_registration_id: "registration-2" } }];
    const result = await saveSettingsPageData({
      saveSettings: async () => ({
        ok: false,
        health: { ok: false, message: "bridge unavailable" },
      }),
      invoke: async () => {
        throw new Error("role updates must wait for a healthy bridge");
      },
      readSettings: async () => createSettingsSnapshot(),
    }, draft);
    assert.deepEqual(result.nextDraft.pendingRoleModelUpdates, draft.pendingRoleModelUpdates);
  });
});
