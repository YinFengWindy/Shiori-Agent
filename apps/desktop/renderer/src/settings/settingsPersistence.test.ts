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
    proactiveStrategies: {},
    models: {
      registrations: overrides.registrations ?? [{ id: "00000000-0000-4000-a000-000000000001", provider: "openai", model: "gpt-main", apiKey: "", baseUrl: "", effort: "none" }],
    },
    channels: {
      telegramToken: "",
      qqBotUin: "",
    },
    memory: {
      enabled: true,
      engine: "default",
      embeddingModel: "",
      embeddingApiKey: "",
      embeddingBaseUrl: "",
      outputDimensionality: "",
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
      consolidationInputTokenThreshold: 75000
    },
  };
}

function createSettingsSnapshot(
  overrides: Partial<SettingsFormData["models"]> = {},
): SettingsSnapshot {
  return {
    configPath: "D:\\Coding\\Shiori\\config.toml",
    generation: 2,
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
            generation: 2,
          };
        },
        readSettings: async () => {
          calls.push("readSettings");
          return persistedSnapshot;
        },
      } satisfies Pick<DesktopApi, "readSettings" | "saveSettings">,
      createSettingsFormData({ registrations: [{ id: "00000000-0000-4000-a000-000000000001", provider: "openai", model: "draft-model", apiKey: "", baseUrl: "", effort: "none" }] }),
    );

    assert.deepEqual(calls, ["saveSettings", "readSettings"]);
    assert.equal(result.snapshot?.formData.models.registrations[0]?.model, "saved-model");
    assert.equal(result.nextDraft.channels.telegramToken, "");
  });

  it("commits deferred role reference changes in the same settings request", async () => {
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
        assert.deepEqual(value.pendingRoleModelUpdates, draft.pendingRoleModelUpdates);
        return { ok: true, generation: 2 };
      },
      readSettings: async () => snapshot,
    }, draft);
    assert.deepEqual(calls, ["save:true"]);
  });

  it("keeps the entire draft and bindings when apply fails without reading stale settings", async () => {
    const draft = createSettingsFormData();
    draft.pendingRoleModelUpdates = [{ roleId: "role-1", runtimeConfig: { dialogue_model_registration_id: "registration-2" } }];
    draft.channels.telegramToken = "unsaved-token";
    const result = await saveSettingsPageData({
      saveSettings: async () => ({
        ok: false,
        error: { code: "runtime_apply_failed", message: "bridge unavailable" },
      }),
      readSettings: async () => { throw new Error("failed apply must not reload settings"); },
    }, draft);
    assert.deepEqual(result.nextDraft, draft);
    assert.equal(result.snapshot, null);
  });
});


describe("core proactive preferences in settings drafts", () => {
  for (const preferences of [{}, { sceneFollowup: false, relationship: false }, { sceneFollowup: true }]) {
    it(`preserves explicit and absent keys through draft cloning: ${JSON.stringify(preferences)}`, async () => {
      const draft = createSettingsFormData();
      draft.proactiveStrategies = preferences;
      const persisted = createSettingsSnapshot();
      persisted.formData.proactiveStrategies = preferences;
      let saves = 0;
      const result = await saveSettingsPageData({
        saveSettings: async (submitted) => {
          saves += 1;
          assert.deepEqual(submitted.proactiveStrategies, preferences);
          assert.notEqual(submitted.proactiveStrategies, draft.proactiveStrategies);
          return { ok: true, generation: 2 };
        },
        readSettings: async () => persisted,
      }, draft);
      assert.equal(saves, 1);
      assert.deepEqual(result.nextDraft.proactiveStrategies, preferences);
      assert.notEqual(result.nextDraft.proactiveStrategies, persisted.formData.proactiveStrategies);
    });
  }
});
